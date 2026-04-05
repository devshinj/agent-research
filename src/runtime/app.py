from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.config.settings import Settings
from src.repository.database import Database
from src.repository.candle_repo import CandleRepository
from src.repository.order_repo import OrderRepository
from src.repository.portfolio_repo import PortfolioRepository
from src.runtime.event_bus import EventBus
from src.runtime.scheduler import Scheduler
from src.service.collector import Collector
from src.service.features import FeatureBuilder
from src.service.paper_engine import PaperEngine
from src.service.portfolio import PortfolioManager
from src.service.predictor import Predictor
from src.service.risk_manager import RiskManager
from src.service.screener import Screener
from src.service.trainer import Trainer
from src.service.upbit_client import UpbitClient
from src.types.events import NewCandleEvent, ScreenedCoinsEvent, SignalEvent, TradeEvent
from src.types.models import PaperAccount

logger = logging.getLogger(__name__)


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.event_bus = EventBus()
        self.scheduler = Scheduler()
        self.paused = False

        # Infrastructure
        self.db = Database(settings.data.db_path)
        self.candle_repo = CandleRepository(self.db)
        self.order_repo = OrderRepository(self.db)
        self.portfolio_repo = PortfolioRepository(self.db)

        # Services
        self.upbit = UpbitClient()
        self.collector = Collector(
            self.upbit, self.candle_repo,
            settings.collector.candle_timeframe, settings.collector.max_candles_per_market,
        )
        self.screener = Screener(settings.screening)
        self.feature_builder = FeatureBuilder()
        self.predictor = Predictor(self.feature_builder, float(settings.strategy.min_confidence))
        self.risk_manager = RiskManager(settings.risk, settings.paper_trading)
        self.paper_engine = PaperEngine(settings.paper_trading)
        self.portfolio_manager = PortfolioManager(settings.risk)
        self.trainer = Trainer(
            self.feature_builder,
            settings.data.model_dir,
            settings.strategy.lookahead_minutes,
            float(settings.strategy.threshold_pct),
        )

        # State
        self.account = PaperAccount(
            initial_balance=settings.paper_trading.initial_balance,
            cash_balance=settings.paper_trading.initial_balance,
            positions={},
        )
        self.screened_markets: list[str] = []

    async def start(self) -> None:
        logger.info("Starting Crypto Paper Trader...")
        await self.db.initialize()

        # Restore persisted state
        saved_account = await self.portfolio_repo.load_account(
            self.settings.paper_trading.initial_balance,
        )
        if saved_account is not None:
            self.account = saved_account
            logger.info(
                "Restored account — cash: %s, positions: %d",
                self.account.cash_balance, len(self.account.positions),
            )

        saved_risk = await self.portfolio_repo.load_risk_state()
        if saved_risk is not None:
            self.risk_manager.load_state(saved_risk)
            logger.info("Restored risk state — %s", saved_risk)

        # Wire event handlers
        self.event_bus.subscribe(SignalEvent, self._on_signal)
        self.event_bus.subscribe(TradeEvent, self._on_trade)

        # Initial data
        await self.collector.refresh_markets()

        # Schedule periodic tasks
        self.scheduler.schedule_interval(
            "collect_candles", self._collect_and_predict,
            interval_seconds=60,
        )
        self.scheduler.schedule_interval(
            "refresh_screening", self._refresh_screening,
            interval_seconds=self.settings.screening.refresh_interval_min * 60,
        )
        self.scheduler.schedule_interval(
            "refresh_markets", self.collector.refresh_markets,
            interval_seconds=self.settings.collector.market_refresh_interval_min * 60,
        )

        logger.info("App started. Seed: %s KRW", self.settings.paper_trading.initial_balance)

    async def stop(self) -> None:
        await self._save_state()
        await self.scheduler.cancel_all()
        await self.upbit.close()
        await self.db.close()
        logger.info("App stopped.")

    async def _refresh_screening(self) -> None:
        tickers = await self.upbit.fetch_tickers(self.collector.markets)
        results = self.screener.screen(tickers, self.collector.korean_names)
        self.screened_markets = [r.market for r in results]
        await self.event_bus.publish(ScreenedCoinsEvent(results, 0))
        logger.info("Screened %d coins: %s", len(results), self.screened_markets)

    async def _collect_and_predict(self) -> None:
        if self.paused or not self.screened_markets:
            return

        await self.collector.collect_candles(self.screened_markets)

        for market in self.screened_markets:
            candles = await self.candle_repo.get_latest(
                market, f"{self.settings.collector.candle_timeframe}m"
            )
            if len(candles) < 60:
                continue

            import pandas as pd
            from decimal import Decimal
            df = pd.DataFrame([
                {"open": float(c.open), "high": float(c.high),
                 "low": float(c.low), "close": float(c.close),
                 "volume": float(c.volume)}
                for c in reversed(candles)
            ])

            try:
                signal = self.predictor.predict(market, df)
                await self.event_bus.publish(SignalEvent(
                    signal.market, signal.signal_type, signal.confidence, signal.timestamp,
                ))
            except KeyError:
                pass  # 모델 미로드

    async def _on_signal(self, event: SignalEvent) -> None:
        from src.types.enums import SignalType
        from decimal import Decimal

        signal_model = __import__("src.types.models", fromlist=["Signal"]).Signal(
            event.market, event.signal_type, event.confidence, event.timestamp,
        )
        approved, reason = self.risk_manager.approve(signal_model, self.account)
        if not approved:
            logger.info("Signal rejected for %s: %s", event.market, reason)
            return

        if event.signal_type == SignalType.BUY:
            invest = self.risk_manager.calculate_position_size(self.account)
            tickers = await self.upbit.fetch_tickers([event.market])
            if not tickers:
                return
            price = tickers[0]["price"]
            order = self.paper_engine.execute_buy(
                self.account, event.market, price, invest, event.confidence,
            )
            await self.order_repo.save(order)
            self.risk_manager.record_trade()
            await self.event_bus.publish(TradeEvent(order, order.created_at))

        elif event.signal_type == SignalType.SELL:
            tickers = await self.upbit.fetch_tickers([event.market])
            if not tickers:
                return
            price = tickers[0]["price"]
            order = self.paper_engine.execute_sell(
                self.account, event.market, price, "ML_SIGNAL",
            )
            await self.order_repo.save(order)
            self.risk_manager.record_trade()
            await self.event_bus.publish(TradeEvent(order, order.created_at))

    async def _on_trade(self, event: TradeEvent) -> None:
        logger.info(
            "Trade executed: %s %s @ %s",
            event.order.side.value, event.order.market, event.order.fill_price,
        )
        await self._save_state()

    async def _save_state(self) -> None:
        await self.portfolio_repo.save_account(self.account)
        await self.portfolio_repo.save_risk_state(self.risk_manager.dump_state())
