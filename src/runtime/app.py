from __future__ import annotations

import asyncio
import dataclasses
import logging
from decimal import Decimal
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from src.config.settings import Settings
from src.repository.candle_repo import CandleRepository
from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.repository.portfolio_repo import PortfolioRepository
from src.repository.signal_repo import SignalRepository
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
from src.types.events import ScreenedCoinsEvent, SignalEvent, TradeEvent
from src.types.models import Candle, PaperAccount

logger = logging.getLogger(__name__)


class App:
    HOT_RELOAD_FIELDS: dict[str, set[str]] = {
        "risk": {
            "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
            "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
        },
        "strategy": {"min_confidence"},
        "screening": {
            "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
            "max_coins", "always_include",
        },
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.event_bus = EventBus()
        self.scheduler = Scheduler()
        self.paused = False
        self._db_lock = asyncio.Lock()

        # Infrastructure
        self.db = Database(settings.data.db_path)
        self.candle_repo = CandleRepository(self.db)
        self.order_repo = OrderRepository(self.db)
        self.portfolio_repo = PortfolioRepository(self.db)
        self.signal_repo = SignalRepository(self.db)

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

    @staticmethod
    def _candles_to_df(candles: Sequence[Candle]) -> pd.DataFrame:
        return pd.DataFrame([
            {"open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close),
             "volume": float(c.volume)}
            for c in reversed(candles)
        ])

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

        # Load existing ML models
        loaded = await self._load_existing_models()
        logger.info("Loaded %d existing models", loaded)

        # Initial data
        await self.collector.refresh_markets()

        # Initial screening + model training
        await self._refresh_screening()
        await self._train_missing_models()

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
        self.scheduler.schedule_interval(
            "retrain_models", self._retrain,
            interval_seconds=self.settings.strategy.retrain_interval_hours * 3600,
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
        timeframe = f"{self.settings.collector.candle_timeframe}m"
        pending: dict[str, pd.DataFrame] = {}

        async with self._db_lock:
            for market in self.screened_markets:
                if market in self.predictor._models:
                    continue
                candles = await self.candle_repo.get_latest(market, timeframe, limit=2000)
                if len(candles) < 200:
                    logger.info("Not enough candles for %s: %d", market, len(candles))
                    continue
                pending[market] = self._candles_to_df(candles)

        for market, df in pending.items():
            result = self.trainer.train(market, df)
            if result["model_path"] is not None:
                self.predictor.load_model(market, result["model_path"])
                logger.info("Trained and loaded model for %s (accuracy: %.3f)", market, result["accuracy"])
            else:
                logger.info("Training skipped for %s: insufficient valid samples", market)

    async def _retrain(self) -> None:
        """Retrain models for all screened markets."""
        if self.paused or not self.screened_markets:
            return

        logger.info("Starting periodic retrain for %d markets", len(self.screened_markets))
        timeframe = f"{self.settings.collector.candle_timeframe}m"
        trained = 0

        async with self._db_lock:
            candle_data: dict[str, pd.DataFrame] = {}
            for market in self.screened_markets:
                candles = await self.candle_repo.get_latest(market, timeframe, limit=2000)
                if len(candles) < 200:
                    continue
                candle_data[market] = self._candles_to_df(candles)

        for market, df in candle_data.items():
            result = self.trainer.train(market, df)
            if result["model_path"] is not None:
                self.predictor.load_model(market, result["model_path"])
                trained += 1

        logger.info("Retrain complete: %d/%d markets updated", trained, len(self.screened_markets))

    async def stop(self) -> None:
        await self._save_state()
        await self.scheduler.cancel_all()
        await self.upbit.close()
        await self.db.close()
        logger.info("App stopped.")

    async def reset(self, new_settings: Settings) -> None:
        """Reset trading data and reinitialize with new settings."""
        self.paused = True
        await self.db.reset_trading_data()

        self.settings = new_settings
        self.risk_manager = RiskManager(new_settings.risk, new_settings.paper_trading)
        self.paper_engine = PaperEngine(new_settings.paper_trading)
        self.portfolio_manager = PortfolioManager(new_settings.risk)
        self.screener = Screener(new_settings.screening)
        self.predictor = Predictor(self.feature_builder, float(new_settings.strategy.min_confidence))
        self.trainer = Trainer(
            self.feature_builder,
            new_settings.data.model_dir,
            new_settings.strategy.lookahead_minutes,
            float(new_settings.strategy.threshold_pct),
        )

        self.account = PaperAccount(
            initial_balance=new_settings.paper_trading.initial_balance,
            cash_balance=new_settings.paper_trading.initial_balance,
        )
        self.paused = False

    def hot_reload(self, patches: dict[str, dict[str, object]]) -> dict[str, list[str]]:
        """Apply partial config update without resetting trading state."""
        for section, fields in patches.items():
            allowed = self.HOT_RELOAD_FIELDS.get(section)
            if allowed is None:
                bad = ", ".join(f"{section}.{k}" for k in fields)
                raise ValueError(f"핫 리로드 불가 필드: {bad} — 완전 초기화를 사용하세요")
            for key in fields:
                if key not in allowed:
                    raise ValueError(
                        f"핫 리로드 불가 필드: {section}.{key} — 완전 초기화를 사용하세요"
                    )

        updated: dict[str, list[str]] = {}

        new_risk = self.settings.risk
        new_screening = self.settings.screening
        new_strategy = self.settings.strategy

        if "risk" in patches:
            coerced = {}
            for k, v in patches["risk"].items():
                field_type = next(
                    f.type for f in dataclasses.fields(type(new_risk)) if f.name == k
                )
                coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(v)
            new_risk = dataclasses.replace(new_risk, **coerced)
            updated["risk"] = list(patches["risk"].keys())

        if "screening" in patches:
            coerced = {}
            for k, v in patches["screening"].items():
                if k == "always_include":
                    coerced[k] = tuple(v) if isinstance(v, list) else v
                else:
                    field_type = next(
                        f.type for f in dataclasses.fields(type(new_screening)) if f.name == k
                    )
                    coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(v)
            new_screening = dataclasses.replace(new_screening, **coerced)
            updated["screening"] = list(patches["screening"].keys())

        if "strategy" in patches:
            coerced = {}
            for k, v in patches["strategy"].items():
                coerced[k] = Decimal(str(v))
            new_strategy = dataclasses.replace(new_strategy, **coerced)
            updated["strategy"] = list(patches["strategy"].keys())

        self.settings = dataclasses.replace(
            self.settings,
            risk=new_risk,
            screening=new_screening,
            strategy=new_strategy,
        )

        if "risk" in patches:
            self.risk_manager.update_config(new_risk)
            self.portfolio_manager._risk = new_risk
        if "strategy" in patches:
            self.predictor.update_min_confidence(float(new_strategy.min_confidence))
        if "screening" in patches:
            self.screener.update_config(new_screening)

        return updated

    async def _refresh_screening(self) -> None:
        tickers = await self.upbit.fetch_tickers(self.collector.markets)
        results = self.screener.screen(tickers, self.collector.korean_names)
        self.screened_markets = [r.market for r in results]
        await self.event_bus.publish(ScreenedCoinsEvent(results, 0))
        logger.info("Screened %d coins: %s", len(results), self.screened_markets)

    async def _collect_and_predict(self) -> None:
        if self.paused or not self.screened_markets:
            return

        async with self._db_lock:
            await self.collector.collect_candles(self.screened_markets)

            for market in self.screened_markets:
                candles = await self.candle_repo.get_latest(
                    market, f"{self.settings.collector.candle_timeframe}m"
                )
                if len(candles) < 60:
                    continue

                df = self._candles_to_df(candles)

                try:
                    signal = self.predictor.predict(market, df)
                    await self.signal_repo.save(
                        signal.market, signal.signal_type.name,
                        signal.confidence, signal.timestamp,
                    )
                    await self.event_bus.publish(SignalEvent(
                        signal.market, signal.signal_type, signal.confidence, signal.timestamp,
                    ))
                except KeyError:
                    pass  # model not loaded

    async def _on_signal(self, event: SignalEvent) -> None:
        from src.types.enums import SignalType

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
