from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from src.repository.candle_repo import CandleRepository
from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.repository.portfolio_repo import PortfolioRepository
from src.repository.signal_repo import SignalRepository
from src.runtime.event_bus import EventBus
from src.runtime.scheduler import Scheduler
from src.service.candle_builder import CandleBuilder
from src.service.features import FeatureBuilder
from src.service.paper_engine import PaperEngine
from src.service.portfolio import PortfolioManager
from src.service.predictor import Predictor
from src.service.risk_manager import RiskManager
from src.service.screener import Screener
from src.service.signal_debouncer import SignalDebouncer
from src.service.tick_stream import TickStream
from src.service.trainer import Trainer
from src.service.upbit_client import UpbitClient
from src.types.enums import SignalType
from src.types.events import NewCandleEvent, ScreenedCoinsEvent, SignalEvent, TradeEvent
from src.types.models import Candle, PaperAccount, Signal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.config.settings import Settings

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
        self.signal_repo = SignalRepository(self.db)

        # Services
        self.upbit = UpbitClient()
        self.tick_stream = TickStream(
            max_markets=settings.tick_stream.max_markets,
            reconnect_max_seconds=settings.tick_stream.reconnect_max_seconds,
        )
        self.candle_builder = CandleBuilder(
            on_candle=lambda c: self.event_bus.publish(NewCandleEvent(c))
        )
        self.screener = Screener(settings.screening)
        self.feature_builder = FeatureBuilder()
        self.predictor = Predictor(self.feature_builder, float(settings.strategy.min_confidence))
        self.signal_debouncer = SignalDebouncer(
            confirm_seconds=settings.strategy.signal_confirm_seconds,
            min_confidence=float(settings.strategy.signal_confirm_min_confidence),
        )
        self.risk_manager = RiskManager(settings.risk, settings.paper_trading)
        self.paper_engine = PaperEngine(settings.paper_trading)
        self.portfolio_manager = PortfolioManager(settings.risk)
        self.trainer = Trainer(
            self.feature_builder,
            settings.data.model_dir,
            settings.strategy.lookahead_seconds,
            float(settings.strategy.threshold_pct),
        )

        # State
        self.account = PaperAccount(
            initial_balance=settings.paper_trading.initial_balance,
            cash_balance=settings.paper_trading.initial_balance,
            positions={},
        )
        self.screened_markets: list[str] = []
        self._all_markets: list[str] = []
        self._korean_names: dict[str, str] = {}

    @staticmethod
    def _candles_to_df(candles: Sequence[Candle]) -> pd.DataFrame:
        return pd.DataFrame([
            {"open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close),
             "volume": float(c.volume)}
            for c in reversed(candles)
        ])

    async def start(self) -> None:
        logger.info("Starting Crypto Paper Trader (tick-based)...")
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
        self.event_bus.subscribe(NewCandleEvent, self._on_new_candle)
        self.event_bus.subscribe(SignalEvent, self._on_signal)
        self.event_bus.subscribe(TradeEvent, self._on_trade)

        # Load existing ML models
        loaded = await self._load_existing_models()
        logger.info("Loaded %d existing models", loaded)

        # Fetch market list and screen
        markets, korean_names = await self.upbit.fetch_markets()
        self._all_markets = markets
        self._korean_names = korean_names
        await self._refresh_screening()

        # Start tick stream
        self.tick_stream.on_tick = self.candle_builder.on_trade
        if self.screened_markets:
            await self.tick_stream.start(self.screened_markets)

        # Schedule periodic tasks
        self.scheduler.schedule_interval(
            "refresh_screening", self._refresh_screening,
            interval_seconds=self.settings.screening.refresh_interval_min * 60,
        )
        self.scheduler.schedule_interval(
            "retrain_models", self._retrain,
            interval_seconds=self.settings.strategy.retrain_interval_hours * 3600,
        )
        self.scheduler.schedule_interval(
            "cleanup_candles", self._cleanup_old_candles,
            interval_seconds=3600,
        )

        logger.info("App started. Seed: %s KRW", self.settings.paper_trading.initial_balance)

    async def _load_existing_models(self) -> int:
        """Load all .pkl models from data/models/ into predictor."""
        model_dir = Path(self.settings.data.model_dir)
        if not model_dir.exists():
            model_dir.mkdir(parents=True, exist_ok=True)
            return 0

        loaded = 0
        for market_dir in model_dir.iterdir():
            if not market_dir.is_dir():
                continue
            # Find most recent model file
            model_files = sorted(market_dir.glob("model_*.pkl"), reverse=True)
            if not model_files:
                continue
            market = market_dir.name.replace("_", "-")
            self.predictor.load_model(market, model_files[0])
            loaded += 1
        return loaded

    async def _train_missing_models(self) -> None:
        """Train models for screened markets that don't have a loaded model."""
        for market in self.screened_markets:
            if market in self.predictor._models:
                continue
            candles = await self.candle_repo.get_latest(market, "1s", limit=5000)
            if len(candles) < 1200:
                logger.info("Not enough candles for %s: %d", market, len(candles))
                continue

            df = self._candles_to_df(candles)
            result = self.trainer.train(market, df)
            if result["model_path"] is not None:
                self.predictor.load_model(market, result["model_path"])
                logger.info("Trained and loaded model for %s (accuracy: %.3f)", market, result["accuracy"])

    async def _retrain(self) -> None:
        """Retrain models for all screened markets."""
        if self.paused or not self.screened_markets:
            return

        logger.info("Starting periodic retrain for %d markets", len(self.screened_markets))
        trained = 0
        for market in self.screened_markets:
            candles = await self.candle_repo.get_latest(market, "1s", limit=5000)
            if len(candles) < 1200:
                continue

            df = self._candles_to_df(candles)
            result = self.trainer.train(market, df)
            if result["model_path"] is not None:
                self.predictor.load_model(market, result["model_path"])
                trained += 1

        logger.info("Retrain complete: %d/%d markets updated", trained, len(self.screened_markets))

    async def stop(self) -> None:
        await self._save_state()
        await self.tick_stream.stop()
        await self.scheduler.cancel_all()
        await self.upbit.close()
        await self.db.close()
        logger.info("App stopped.")

    async def reset(self, new_settings: Settings) -> None:
        """Reset trading data and reinitialize with new settings."""
        self.paused = True
        await self.tick_stream.stop()
        await self.db.reset_trading_data()

        self.settings = new_settings
        self.risk_manager = RiskManager(new_settings.risk, new_settings.paper_trading)
        self.paper_engine = PaperEngine(new_settings.paper_trading)
        self.portfolio_manager = PortfolioManager(new_settings.risk)
        self.screener = Screener(new_settings.screening)
        self.predictor = Predictor(self.feature_builder, float(new_settings.strategy.min_confidence))
        self.signal_debouncer = SignalDebouncer(
            confirm_seconds=new_settings.strategy.signal_confirm_seconds,
            min_confidence=float(new_settings.strategy.signal_confirm_min_confidence),
        )
        self.trainer = Trainer(
            self.feature_builder,
            new_settings.data.model_dir,
            new_settings.strategy.lookahead_seconds,
            float(new_settings.strategy.threshold_pct),
        )

        self.account = PaperAccount(
            initial_balance=new_settings.paper_trading.initial_balance,
            cash_balance=new_settings.paper_trading.initial_balance,
        )
        self.paused = False

    async def _refresh_screening(self) -> None:
        tickers = await self.upbit.fetch_tickers(self._all_markets)
        results = self.screener.screen(tickers, self._korean_names)
        old_markets = self.screened_markets
        self.screened_markets = [r.market for r in results][: self.settings.tick_stream.max_markets]
        await self.event_bus.publish(ScreenedCoinsEvent(results, 0))
        logger.info("Screened %d coins, tracking: %s", len(results), self.screened_markets)

        # Update tick stream subscription if markets changed
        if self.screened_markets != old_markets and self.tick_stream._running:
            await self.tick_stream.update_markets(self.screened_markets)

    async def _on_new_candle(self, event: NewCandleEvent) -> None:
        """Handle completed candles — predict on 1s candles, save all to DB."""
        candle = event.candle

        # Save all candles to DB
        await self.candle_repo.save(candle)

        # Only predict on 1s candles
        if candle.timeframe != "1s" or self.paused:
            return

        market = candle.market
        candles = self.candle_builder.get_recent(market, "1s", limit=300)
        if len(candles) < 60:
            return

        df = self._candles_to_df(candles)

        try:
            signal = self.predictor.predict(market, df)
            await self.signal_repo.save(
                signal.market, signal.signal_type.name,
                signal.confidence, signal.timestamp,
            )

            confirmed = self.signal_debouncer.on_raw_signal(signal)
            if confirmed is not None:
                await self.event_bus.publish(SignalEvent(
                    confirmed.market, confirmed.signal_type,
                    confirmed.confidence, confirmed.timestamp,
                ))
        except KeyError:
            pass  # model not loaded

    async def _cleanup_old_candles(self) -> None:
        """Delete candles older than retention window."""
        retention_seconds = self.settings.tick_stream.candle_retention_hours * 3600
        cutoff = int(time.time()) - retention_seconds
        deleted = await self.candle_repo.delete_older_than(cutoff)
        if deleted:
            logger.info("Cleaned up %d old candles", deleted)

    async def _on_signal(self, event: SignalEvent) -> None:
        signal_model = Signal(
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
