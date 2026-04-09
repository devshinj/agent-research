from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.settings import Settings
from src.repository.candle_repo import CandleRepository
from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.repository.pending_order_repo import PendingOrderRepo
from src.repository.portfolio_repo import PortfolioRepository
from src.repository.ranking_repo import RankingRepo
from src.repository.signal_repo import SignalRepository
from src.repository.user_repo import UserRepo
from src.runtime.event_bus import EventBus
from src.runtime.scheduler import Scheduler
from src.service.collector import Collector
from src.service.entry_analyzer import EntryAnalyzer
from src.service.features import FeatureBuilder
from src.service.paper_engine import PaperEngine
from src.service.portfolio import PortfolioManager
from src.service.predictor import Predictor
from src.service.risk_manager import RiskManager
from src.service.screener import Screener
from src.service.trainer import Trainer
from src.service.upbit_client import UpbitClient
from src.service.upbit_ws import UpbitWebSocketService
from src.types.events import ScreenedCoinsEvent, SignalEvent, TradeEvent
from src.types.models import Candle, DailySummary, PaperAccount

logger = logging.getLogger(__name__)


class App:
    HOT_RELOAD_FIELDS: dict[str, set[str]] = {
        "risk": {
            "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
            "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
            "partial_take_profit_pct", "partial_sell_fraction",
        },
        "strategy": {"min_confidence", "threshold_pct"},
        "screening": {
            "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
            "max_coins", "always_include",
        },
        "paper_trading": {
            "max_position_pct", "max_open_positions",
            "max_additional_buys", "additional_buy_drop_pct", "additional_buy_ratio",
        },
        "entry_analyzer": {"enabled", "min_entry_score", "price_lookback_candles"},
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.event_bus = EventBus()
        self.scheduler = Scheduler()
        self.paused = True
        self.trading_enabled = False
        self._db_lock = asyncio.Lock()

        # Infrastructure
        self.db = Database(settings.data.db_path)
        self.candle_repo = CandleRepository(self.db)
        self.order_repo = OrderRepository(self.db)
        self.portfolio_repo = PortfolioRepository(self.db)
        self.signal_repo = SignalRepository(self.db)
        self.pending_order_repo = PendingOrderRepo(self.db)
        from src.repository.notification_repo import NotificationRepo
        self.notification_repo = NotificationRepo(self.db)

        # Services
        self.upbit = UpbitClient()
        self.upbit_ws = UpbitWebSocketService(self.upbit)
        self.collector = Collector(
            self.upbit, self.candle_repo,
            settings.collector.candle_timeframe, settings.collector.max_candles_per_market,
            train_timeframe=settings.collector.train_timeframe,
            train_candles=settings.collector.train_candles,
            daily_candles=settings.collector.daily_candles,
            context_timeframes=settings.collector.context_timeframes,
        )
        self.screener = Screener(settings.screening)
        self.feature_builder = FeatureBuilder()
        self.predictor = Predictor(self.feature_builder, float(settings.strategy.min_confidence))
        self.risk_manager = RiskManager(settings.risk, settings.paper_trading)
        self.paper_engine = PaperEngine(settings.paper_trading)
        self.portfolio_manager = PortfolioManager(settings.risk)
        self.entry_analyzer = EntryAnalyzer(settings.entry_analyzer)
        self.trainer = Trainer(
            self.feature_builder,
            settings.data.model_dir,
            settings.strategy.lookahead_minutes,
            float(settings.strategy.threshold_pct),
            train_timeframe=settings.collector.train_timeframe,
        )

        # State (kept as fallback)
        self.account = PaperAccount(
            initial_balance=settings.paper_trading.initial_balance,
            cash_balance=settings.paper_trading.initial_balance,
            positions={},
        )
        self.screened_markets: list[str] = []
        self.training_in_progress: dict[str, float] = {}  # market -> start epoch
        self._ws_outbox: dict[int, list[dict[str, object]]] = {}

        # Multi-user state
        self.user_accounts: dict[int, PaperAccount] = {}
        self.user_risk: dict[int, RiskManager] = {}
        self.user_pnl: dict[int, dict] = {}  # {user_id: {realized, wins, losses}}

        # User repository
        self.user_repo = UserRepo(self.db)
        self.ranking_repo = RankingRepo(self.db)

    MAX_WS_OUTBOX_PER_USER = 100

    def _push_ws_message(self, user_id: int, msg: dict[str, object]) -> None:
        queue = self._ws_outbox.setdefault(user_id, [])
        queue.append(msg)
        if len(queue) > self.MAX_WS_OUTBOX_PER_USER:
            self._ws_outbox[user_id] = queue[-self.MAX_WS_OUTBOX_PER_USER:]

    def _pop_ws_messages(self, user_id: int) -> list[dict[str, object]]:
        return self._ws_outbox.pop(user_id, [])

    def _clear_ws_outbox(self, user_id: int) -> None:
        self._ws_outbox.pop(user_id, None)

    @staticmethod
    def _candles_to_df(candles: Sequence[Candle]) -> pd.DataFrame:
        return pd.DataFrame([
            {"open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close),
             "volume": float(c.volume)}
            for c in reversed(candles)
        ])

    async def load_user(self, user_id: int) -> None:
        """Load or reload a user's account and risk manager."""
        settings_row = await self.user_repo.get_settings(user_id)
        if not settings_row:
            return

        # Load account from DB
        account = await self.portfolio_repo.load_account(user_id)
        if account is None:
            initial = Decimal(settings_row["initial_balance"])
            account = PaperAccount(
                initial_balance=initial, cash_balance=initial,
            )
        self.user_accounts[user_id] = account

        # Load risk manager with user settings
        risk_config = dataclasses.replace(
            self.settings.risk,
            stop_loss_pct=Decimal(settings_row["stop_loss_pct"]),
            take_profit_pct=Decimal(settings_row["take_profit_pct"]),
            trailing_stop_pct=Decimal(settings_row["trailing_stop_pct"]),
            max_daily_loss_pct=Decimal(settings_row["max_daily_loss_pct"]),
        )
        rm = RiskManager(risk_config, self.settings.paper_trading)
        risk_state = await self.portfolio_repo.load_risk_state(user_id)
        if risk_state:
            rm.load_state(risk_state)
        self.user_risk[user_id] = rm

        # Init daily PnL tracking
        self.user_pnl[user_id] = {
            "realized": Decimal("0"), "wins": 0, "losses": 0,
        }

    async def start(self) -> None:
        logger.info("Starting Crypto Paper Trader...")
        await self.db.initialize()

        # Load all active users
        active_ids = await self.user_repo.get_active_user_ids()
        for uid in active_ids:
            await self.load_user(uid)
        logger.info("Loaded %d active users", len(active_ids))

        # Wire event handlers
        self.event_bus.subscribe(SignalEvent, self._on_signal)
        self.event_bus.subscribe(TradeEvent, self._on_trade)

        # Load existing ML models
        loaded = await self._load_existing_models()
        logger.info("Loaded %d existing models", loaded)

        # Cleanup stale data on startup
        await self._cleanup_stale_data()

        # Recover pending limit orders
        await self._recover_pending_orders()

        # Initial data
        await self.collector.refresh_markets()

        # Initial screening + seed candles + model training
        await self._refresh_screening()
        if self.screened_markets:
            logger.info("Seeding candle history for %d screened markets...", len(self.screened_markets))
            await self.collector.collect_candles(self.screened_markets)
            logger.info("Seeding training data (5m) for %d markets...", len(self.screened_markets))
            await self.collector.collect_train_candles(self.screened_markets)
            logger.info("Seeding all context timeframes for %d markets...", len(self.screened_markets))
            await self.collector.collect_all_context(self.screened_markets)
        await self._train_missing_models()

        # Schedule periodic tasks
        self.scheduler.schedule_interval(
            "monitor_positions", self._monitor_positions,
            interval_seconds=10,
        )
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
        # Context 타임프레임별 수집 스케줄
        scheduled_intervals: set[int] = set()
        for ct in self.settings.collector.context_timeframes:
            if ct.interval_sec not in scheduled_intervals and ct.interval_sec != 60:
                self.scheduler.schedule_interval(
                    f"collect_ctx_{ct.interval_sec}s",
                    lambda iv=ct.interval_sec: self._collect_context(iv),
                    interval_seconds=ct.interval_sec,
                )
                scheduled_intervals.add(ct.interval_sec)
        # 일봉 + 학습 메인(5분봉)은 1시간마다
        self.scheduler.schedule_interval(
            "collect_train_data", self._collect_train_data,
            interval_seconds=3600,
        )
        self.scheduler.schedule_interval(
            "cleanup_stale_data", self._cleanup_stale_data,
            interval_seconds=6 * 3600,  # every 6 hours
        )

        # Start Upbit WebSocket for live ticker data
        all_markets = self.collector.markets
        if all_markets:
            await self.upbit_ws.start(all_markets)
            logger.info("Upbit WebSocket started for %d markets", len(all_markets))

        self.paused = False
        logger.info(
            "App started. Seed: %s KRW | Auto-trading: OFF (enable from System page)",
            self.settings.paper_trading.initial_balance,
        )

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

    async def _build_context_dfs(self, market: str) -> dict[str, pd.DataFrame]:
        """DB에서 각 context 타임프레임의 캔들을 조회하여 dict로 반환."""
        context_dfs: dict[str, pd.DataFrame] = {}
        for ct in self.settings.collector.context_timeframes:
            tf_str = f"{ct.minutes}m"
            candles = await self.candle_repo.get_latest(market, tf_str, ct.candles)
            if len(candles) >= 20:
                context_dfs[tf_str] = self._candles_to_df(candles)
        daily = await self.candle_repo.get_latest(
            market, "1D", self.settings.collector.daily_candles,
        )
        if len(daily) >= 20:
            context_dfs["1D"] = self._candles_to_df(daily)
        return context_dfs

    async def _train_missing_models(self) -> None:
        """Train models for screened markets that don't have a loaded model."""
        train_tf = f"{self.settings.collector.train_timeframe}m"
        pending: dict[str, tuple[pd.DataFrame, dict[str, pd.DataFrame]]] = {}

        async with self._db_lock:
            for market in self.screened_markets:
                if market in self.predictor._models:
                    continue
                candles = await self.candle_repo.get_latest(
                    market, train_tf, self.settings.collector.train_candles,
                )
                if len(candles) < 200:
                    logger.info("Not enough %s candles for %s: %d", train_tf, market, len(candles))
                    continue
                df = self._candles_to_df(candles)
                context_dfs = await self._build_context_dfs(market)
                pending[market] = (df, context_dfs)

        for market, (df, context_dfs) in pending.items():
            self.training_in_progress[market] = time.time()
            try:
                result = self.trainer.train(market, df, context_dfs=context_dfs or None)
                if result["model_path"] is not None:
                    self.predictor.load_model(market, result["model_path"])
                    logger.info(
                        "Trained and loaded model for %s (f1: %.3f, accuracy: %.3f)",
                        market, result["f1"], result["accuracy"],
                    )
                else:
                    logger.info("Training skipped for %s: insufficient valid samples", market)
            finally:
                self.training_in_progress.pop(market, None)

    async def _retrain(self) -> None:
        """Retrain models for all screened markets one at a time to limit memory."""
        if not self.screened_markets:
            return

        logger.info("Starting periodic retrain for %d markets", len(self.screened_markets))
        train_tf = f"{self.settings.collector.train_timeframe}m"
        trained = 0
        total = 0

        for market in list(self.screened_markets):
            async with self._db_lock:
                candles = await self.candle_repo.get_latest(
                    market, train_tf, self.settings.collector.train_candles,
                )
                context_dfs = await self._build_context_dfs(market)
            if len(candles) < 200:
                continue
            total += 1
            df = self._candles_to_df(candles)

            self.training_in_progress[market] = time.time()
            try:
                result = self.trainer.train(market, df, context_dfs=context_dfs or None)
                if result["model_path"] is not None:
                    self.predictor.load_model(market, result["model_path"])
                    trained += 1
            finally:
                self.training_in_progress.pop(market, None)
            del df

        logger.info("Retrain complete: %d/%d markets updated", trained, total)

    async def stop(self) -> None:
        await self._save_all_states()
        await self.scheduler.cancel_all()
        await self.upbit_ws.stop()
        await self.upbit.close()
        await self.db.close()
        logger.info("App stopped.")

    async def reset(self, new_settings: Settings, user_id: int | None = None) -> None:
        """Reset trading data and reinitialize with new settings."""
        self.paused = True
        await self.db.reset_trading_data(user_id)

        if user_id is None:
            # Full reset (admin)
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
                train_timeframe=new_settings.collector.train_timeframe,
            )
            self.account = PaperAccount(
                initial_balance=new_settings.paper_trading.initial_balance,
                cash_balance=new_settings.paper_trading.initial_balance,
            )
            self.user_accounts.clear()
            self.user_risk.clear()
            self.user_pnl.clear()
            loaded = await self._load_existing_models()
            logger.info("Reset: loaded %d existing models", loaded)
            await self._refresh_screening()
            await self._train_missing_models()
        else:
            # Per-user reset
            await self.load_user(user_id)
            # Persist new account to DB so ranking query sees it immediately
            if user_id in self.user_accounts:
                await self.portfolio_repo.save_account(
                    self.user_accounts[user_id], user_id
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
        new_pt = self.settings.paper_trading
        new_ea = self.settings.entry_analyzer

        if "risk" in patches:
            coerced: dict[str, Any] = {}
            for k, v in patches["risk"].items():
                field_type = next(
                    f.type for f in dataclasses.fields(type(new_risk)) if f.name == k
                )
                coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(str(v))
            new_risk = dataclasses.replace(new_risk, **coerced)
            updated["risk"] = list(patches["risk"].keys())

        if "screening" in patches:
            s_coerced: dict[str, Any] = {}
            for k, v in patches["screening"].items():
                if k == "always_include":
                    s_coerced[k] = tuple(v) if isinstance(v, list) else v
                else:
                    field_type = next(
                        f.type for f in dataclasses.fields(type(new_screening)) if f.name == k
                    )
                    s_coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(str(v))
            new_screening = dataclasses.replace(new_screening, **s_coerced)
            updated["screening"] = list(patches["screening"].keys())

        if "strategy" in patches:
            st_coerced: dict[str, Any] = {}
            for k, v in patches["strategy"].items():
                st_coerced[k] = Decimal(str(v))
            new_strategy = dataclasses.replace(new_strategy, **st_coerced)
            updated["strategy"] = list(patches["strategy"].keys())

        if "paper_trading" in patches:
            pt_coerced: dict[str, Any] = {}
            for k, v in patches["paper_trading"].items():
                field_type = next(
                    f.type for f in dataclasses.fields(type(new_pt)) if f.name == k
                )
                pt_coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(str(v))
            new_pt = dataclasses.replace(new_pt, **pt_coerced)
            updated["paper_trading"] = list(patches["paper_trading"].keys())

        if "entry_analyzer" in patches:
            ea_coerced: dict[str, Any] = {}
            for k, v in patches["entry_analyzer"].items():
                if k == "enabled":
                    ea_coerced[k] = bool(v)
                else:
                    ea_coerced[k] = Decimal(str(v)) if k == "min_entry_score" else int(str(v))
            new_ea = dataclasses.replace(new_ea, **ea_coerced)
            updated["entry_analyzer"] = list(patches["entry_analyzer"].keys())

        self.settings = dataclasses.replace(
            self.settings,
            risk=new_risk,
            screening=new_screening,
            strategy=new_strategy,
            paper_trading=new_pt,
            entry_analyzer=new_ea,
        )

        if "risk" in patches:
            self.risk_manager.update_config(new_risk)
            self.portfolio_manager._risk = new_risk
        if "strategy" in patches:
            self.predictor.update_min_confidence(float(new_strategy.min_confidence))
            if "threshold_pct" in patches["strategy"]:
                self.trainer.update_threshold(float(new_strategy.threshold_pct))
                coro = self._retrain()
                try:
                    asyncio.create_task(coro)
                except RuntimeError:
                    coro.close()
                    logger.info("No running event loop; skipping auto-retrain")
        if "screening" in patches:
            self.screener.update_config(new_screening)
        if "paper_trading" in patches:
            self.risk_manager._pt = new_pt
            self.paper_engine.update_config(new_pt)

        return updated

    async def _cleanup_stale_data(self) -> None:
        """Delete stale candles, orders, signals, screening logs, and old model files."""
        now = int(time.time())
        day_seconds = 86400

        candle_cutoff = now - self.settings.data.stale_candle_days * day_seconds
        order_cutoff = now - self.settings.data.stale_order_days * day_seconds
        signal_cutoff = now - self.settings.data.stale_candle_days * day_seconds
        screening_cutoff = now - self.settings.data.stale_candle_days * day_seconds

        async with self._db_lock:
            candles_deleted = await self.candle_repo.delete_older_than(candle_cutoff)
            orders_deleted = await self.order_repo.delete_older_than(order_cutoff)
            signals_deleted = await self.signal_repo.delete_older_than(signal_cutoff)
            screening_deleted = await self.db.delete_screening_log_older_than(screening_cutoff)

        total = candles_deleted + orders_deleted + signals_deleted + screening_deleted
        if total > 0:
            logger.info(
                "Stale data cleanup: candles=%d, orders=%d, signals=%d, screening=%d",
                candles_deleted, orders_deleted, signals_deleted, screening_deleted,
            )

        # Clean up old model files (keep only the latest per market)
        model_dir = Path(self.settings.data.model_dir)
        model_cutoff = now - self.settings.data.stale_model_days * day_seconds
        models_removed = 0
        if model_dir.exists():
            for market_dir in model_dir.iterdir():
                if not market_dir.is_dir():
                    continue
                model_files = sorted(market_dir.glob("model_*.pkl"), reverse=True)
                # Keep the latest, remove old ones past stale_model_days
                for pkl in model_files[1:]:
                    if pkl.stat().st_mtime < model_cutoff:
                        pkl.unlink()
                        models_removed += 1
        if models_removed > 0:
            logger.info("Stale model cleanup: %d old model files removed", models_removed)

    async def _refresh_screening(self) -> None:
        tickers = await self.upbit.fetch_tickers(self.collector.markets)
        results = self.screener.screen(tickers, self.collector.korean_names)
        self.screened_markets = [r.market for r in results]
        await self.event_bus.publish(ScreenedCoinsEvent(results, 0))
        logger.info("Screened %d coins: %s", len(results), self.screened_markets)

    async def _collect_and_predict(self) -> None:
        if not self.screened_markets:
            logger.warning("No screened markets — skipping signal generation")
            return

        async with self._db_lock:
            await self.collector.collect_candles(self.screened_markets)

            for market in self.screened_markets:
                candles = await self.candle_repo.get_latest(
                    market, f"{self.settings.collector.candle_timeframe}m",
                    self.settings.collector.max_candles_per_market,
                )
                if len(candles) < 60:
                    logger.warning(
                        "%s: insufficient candles (%d/60) — skipping prediction",
                        market, len(candles),
                    )
                    continue

                df = self._candles_to_df(candles)
                context_dfs = await self._build_context_dfs(market)

                try:
                    signal, basis = self.predictor.predict(
                        market, df, context_dfs=context_dfs or None,
                    )
                    basis_json: str | None = None
                    if basis.top_features:
                        basis_json = json.dumps([
                            {"feature": f, "shap": round(s, 4), "value": round(v, 4)}
                            for f, s, v in basis.top_features
                        ])
                    await self.signal_repo.save(
                        signal.market, signal.signal_type.name,
                        signal.confidence, signal.timestamp, basis_json,
                    )
                    await self.event_bus.publish(SignalEvent(
                        signal.market, signal.signal_type, signal.confidence, signal.timestamp,
                    ))
                except KeyError:
                    logger.warning("%s: no trained model loaded — skipping prediction", market)

    async def _collect_train_data(self) -> None:
        """학습 메인 타임프레임(5m) + 일봉 수집."""
        if not self.screened_markets:
            return
        async with self._db_lock:
            await self.collector.collect_train_candles(self.screened_markets)

    async def _collect_context(self, interval_sec: int) -> None:
        """특정 interval에 해당하는 context 타임프레임 수집."""
        if not self.screened_markets:
            return
        async with self._db_lock:
            await self.collector.collect_context_candles(self.screened_markets, interval_sec)

    async def _on_signal(self, event: SignalEvent) -> None:
        if self.paused:
            return

        signal_model = __import__("src.types.models", fromlist=["Signal"]).Signal(
            event.market, event.signal_type, event.confidence, event.timestamp,
        )

        for user_id, account in list(self.user_accounts.items()):
            settings_row = await self.user_repo.get_settings(user_id)
            if not settings_row or not settings_row["trading_enabled"]:
                continue

            rm = self.user_risk.get(user_id)
            if rm is None:
                continue

            await self._process_signal_for_user(
                event, signal_model, user_id, account, rm,
            )

    async def _process_signal_for_user(
        self, event: SignalEvent, signal_model: Any,
        user_id: int, account: PaperAccount, rm: RiskManager,
    ) -> None:
        from src.types.enums import SignalType

        approved, reason = rm.approve(signal_model, account)
        if not approved:
            await self.notification_repo.save(
                user_id, event.market, event.signal_type.name, "REJECTED",
                reason, event.confidence,
            )
            return

        if event.signal_type == SignalType.BUY:
            existing = account.positions.get(event.market)
            is_additional = existing is not None

            if is_additional:
                assert existing is not None
                tickers = await self.upbit.fetch_tickers([event.market])
                if not tickers:
                    return
                price = tickers[0]["price"]
                if not rm.should_additional_buy(existing, price):
                    await self.notification_repo.save(
                        user_id, event.market, "BUY", "REJECTED",
                        "추가매수 조건 미충족", event.confidence,
                    )
                    return
            else:
                tickers = await self.upbit.fetch_tickers([event.market])
                if not tickers:
                    return
                price = tickers[0]["price"]

            if not is_additional and self.settings.entry_analyzer.enabled:
                async with self._db_lock:
                    candles = await self.candle_repo.get_latest(
                        event.market, f"{self.settings.collector.candle_timeframe}m",
                    )
                if len(candles) >= self.settings.entry_analyzer.price_lookback_candles:
                    df = self._candles_to_df(candles)
                    features = self.feature_builder.build(df)
                    entry_score = self.entry_analyzer.score_entry(df, features)
                    if entry_score < self.settings.entry_analyzer.min_entry_score:
                        await self.notification_repo.save(
                            user_id, event.market, "BUY", "REJECTED",
                            f"진입 스코어 부족 ({float(entry_score):.2f} < {float(self.settings.entry_analyzer.min_entry_score):.2f})",
                            event.confidence,
                        )
                        return

            invest = rm.calculate_position_size(
                account, Decimal(str(event.confidence)),
                is_additional=is_additional,
            )
            order = self.paper_engine.execute_buy(
                account, event.market, price, invest, event.confidence,
            )
            await self.order_repo.save(order, user_id)
            rm.record_trade()
            await self.notification_repo.save(
                user_id, event.market, "BUY", "SUCCESS",
                f"매수 완료 — {int(invest):,}원, 신뢰도 {event.confidence:.0%}",
                event.confidence,
            )
            await self.event_bus.publish(TradeEvent(order, order.created_at))

        elif event.signal_type == SignalType.SELL:
            position = account.positions.get(event.market)
            if position is None:
                return
            if position.trade_mode == "MANUAL":
                return
            tickers = await self.upbit.fetch_tickers([event.market])
            if not tickers:
                return
            price = tickers[0]["price"]
            entry_price = position.entry_price
            quantity = position.quantity
            pnl_pct = (price - entry_price) / entry_price * 100
            order = self.paper_engine.execute_sell(
                account, event.market, price, "ML_SIGNAL",
            )
            await self.order_repo.save(order, user_id)
            rm.record_trade()
            self._record_trade_result_for_user(
                user_id, entry_price, order.fill_price, quantity,
            )
            await self.notification_repo.save(
                user_id, event.market, "SELL", "SUCCESS",
                f"매도 완료 — 수익률 {float(pnl_pct):+.1f}%",
                event.confidence,
            )
            await self.event_bus.publish(TradeEvent(order, order.created_at))

    async def _on_trade(self, event: TradeEvent) -> None:
        logger.info(
            "Trade executed: %s %s @ %s",
            event.order.side.value, event.order.market, event.order.fill_price,
        )
        await self._save_all_states()

    async def _recover_pending_orders(self) -> None:
        """Recover pending orders on server restart: expire overdue, log active."""
        for user_id, account in self.user_accounts.items():
            expired = await self.pending_order_repo.expire_all(user_id, account)
            if expired:
                logger.info("Expired %d pending orders for user %d on startup", expired, user_id)
                await self.portfolio_repo.save_account(account, user_id)

        active = await self.pending_order_repo.get_all_pending()
        if active:
            logger.info("Recovered %d active pending orders", len(active))

    async def _monitor_positions(self) -> None:
        if self.paused:
            return

        for user_id, account in list(self.user_accounts.items()):
            if not account.positions:
                continue

            settings_row = await self.user_repo.get_settings(user_id)
            if not settings_row or not settings_row["trading_enabled"]:
                continue

            rm = self.user_risk.get(user_id)
            if rm is None:
                continue

            await self._monitor_user_positions(user_id, account, rm)

        # Check pending limit orders
        await self._check_pending_orders()

    async def _monitor_user_positions(
        self, user_id: int, account: PaperAccount, rm: RiskManager,
    ) -> None:
        markets = list(account.positions.keys())
        tickers = await self.upbit.fetch_tickers(markets)
        price_map: dict[str, Decimal] = {t["market"]: t["price"] for t in tickers}

        exits: list[tuple[str, Decimal, str]] = []
        partial_exits: list[tuple[str, Decimal, Decimal]] = []

        for market, position in account.positions.items():
            price = price_map.get(market)
            if price is None:
                continue

            self.portfolio_manager.update_position(position, price)

            # MANUAL positions
            if position.trade_mode == "MANUAL":
                manual_reason = self.portfolio_manager.check_manual_exit(position, price)
                if manual_reason is not None:
                    exits.append((market, price, manual_reason))
                continue

            # AUTO positions
            pnl_pct = (price - position.entry_price) / position.entry_price
            if pnl_pct <= -self.settings.risk.stop_loss_pct:
                exits.append((market, price, "STOP_LOSS"))
                continue
            fraction = self.portfolio_manager.check_partial_exit(position, price)
            if fraction is not None:
                partial_exits.append((market, price, fraction))
                continue
            reason = self.portfolio_manager.check_exit_conditions(position, price)
            if reason is not None:
                exits.append((market, price, reason))

        for market, price, reason in exits:
            position = account.positions[market]
            entry_price = position.entry_price
            quantity = position.quantity
            pnl_pct = (price - entry_price) / entry_price * 100
            order = self.paper_engine.execute_sell(account, market, price, reason)
            await self.order_repo.save(order, user_id)
            rm.record_trade()
            self._record_trade_result_for_user(user_id, entry_price, price, quantity)
            reason_label = {"STOP_LOSS": "손절", "TAKE_PROFIT": "익절", "TRAILING_STOP": "트레일링"}.get(reason, reason)
            await self.notification_repo.save(
                user_id, market, "SELL", "SUCCESS",
                f"{reason_label} 발동 — 수익률 {float(pnl_pct):+.1f}%",
            )
            await self.event_bus.publish(TradeEvent(order, order.created_at))
            self._push_ws_message(user_id, {
                "type": "order_filled",
                "data": {
                    "market": order.market, "side": order.side.value,
                    "reason": order.reason, "price": str(order.fill_price),
                },
            })

        for market, price, fraction in partial_exits:
            position = account.positions[market]
            entry_price = position.entry_price
            sell_quantity = position.quantity * fraction
            order = self.paper_engine.execute_partial_sell(
                account, market, price, fraction,
            )
            await self.order_repo.save(order, user_id)
            self._record_trade_result_for_user(user_id, entry_price, price, sell_quantity)
            await self.event_bus.publish(TradeEvent(order, order.created_at))
            self._push_ws_message(user_id, {
                "type": "order_filled",
                "data": {
                    "market": order.market, "side": order.side.value,
                    "reason": order.reason, "price": str(order.fill_price),
                },
            })

    async def _check_pending_orders(self) -> None:
        """Check all pending limit orders for fill conditions and expiry."""
        pending = await self.pending_order_repo.get_all_pending()
        if not pending:
            return

        now = int(time.time())

        for po in pending:
            account = self.user_accounts.get(po.user_id)
            if account is None:
                continue

            # Expire check
            if po.expires_at < now:
                expired = await self.pending_order_repo.expire_all(po.user_id, account)
                if expired:
                    await self._save_user_state(po.user_id)
                    self._push_ws_message(po.user_id, {
                        "type": "pending_order_expired",
                        "data": {"order_id": po.id, "market": po.market},
                    })
                continue

            # Fill check: current_price <= limit_price
            price = self.upbit_ws.get_price(po.market)
            if price is None:
                continue

            if price <= po.limit_price:
                filled = await self.pending_order_repo.fill(po.id)
                if not filled:
                    continue  # Already processed (CAS)

                order, refund = self.paper_engine.execute_limit_buy(
                    account, po.market, price, po.amount_krw, reason="LIMIT_BUY",
                )

                await self.order_repo.save(order, po.user_id)
                rm = self.user_risk.get(po.user_id)
                if rm:
                    rm.record_trade()
                await self._save_user_state(po.user_id)

                self._push_ws_message(po.user_id, {
                    "type": "pending_order_filled",
                    "data": {
                        "order_id": po.id,
                        "market": order.market,
                        "side": order.side.value,
                        "price": str(order.fill_price),
                        "quantity": str(order.quantity),
                        "refund": str(refund),
                    },
                })
                logger.info(
                    "Limit order %s filled: %s @ %s for user %d",
                    po.id, po.market, price, po.user_id,
                )

    def _record_trade_result_for_user(
        self, user_id: int, entry_price: Decimal, fill_price: Decimal, quantity: Decimal,
    ) -> None:
        rm = self.user_risk.get(user_id)
        pnl_data = self.user_pnl.get(user_id)
        if not rm or pnl_data is None:
            return

        realized = (fill_price - entry_price) * quantity
        pnl_data["realized"] += realized

        if fill_price >= entry_price:
            rm.record_win()
            pnl_data["wins"] += 1
        else:
            rm.record_loss()
            pnl_data["losses"] += 1
            loss_pct = (entry_price - fill_price) / entry_price
            rm.record_daily_loss(loss_pct)

    async def _save_user_state(self, user_id: int) -> None:
        account = self.user_accounts.get(user_id)
        rm = self.user_risk.get(user_id)
        if not account or not rm:
            return
        await self.portfolio_repo.save_account(account, user_id)
        await self.portfolio_repo.save_risk_state(rm.dump_state(), user_id)
        await self._snapshot_daily_summary_for_user(user_id)

    async def _save_all_states(self) -> None:
        for user_id in list(self.user_accounts.keys()):
            await self._save_user_state(user_id)

    async def _snapshot_daily_summary_for_user(self, user_id: int) -> None:
        from datetime import date as date_cls

        account = self.user_accounts.get(user_id)
        rm = self.user_risk.get(user_id)
        pnl_data = self.user_pnl.get(user_id)
        if not account or not rm or pnl_data is None:
            return

        today = date_cls.today().isoformat()

        current_prices: dict[str, Decimal] = {}
        if account.positions:
            tickers = await self.upbit.fetch_tickers(list(account.positions.keys()))
            for t in tickers:
                current_prices[t["market"]] = t["price"]
        total_equity = self.portfolio_manager.calculate_total_equity(
            account, current_prices,
        )

        existing = await self.portfolio_repo.get_daily_summary(today, user_id)
        starting = existing.starting_balance if existing else total_equity

        risk_state = rm.dump_state()
        total_trades = int(risk_state["daily_trades"])
        realized = pnl_data["realized"]
        win_trades = pnl_data["wins"]
        loss_trades = pnl_data["losses"]

        drawdown_pct = (
            ((starting - total_equity) / starting * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if starting > 0 else Decimal(0)
        )
        prev_max = existing.max_drawdown_pct if existing else Decimal(0)
        max_drawdown = max(drawdown_pct, prev_max)

        summary = DailySummary(
            date=today,
            starting_balance=starting,
            ending_balance=total_equity,
            realized_pnl=realized,
            total_trades=total_trades,
            win_trades=win_trades,
            loss_trades=loss_trades,
            max_drawdown_pct=max_drawdown,
        )
        await self.portfolio_repo.save_daily_summary(summary, user_id)
