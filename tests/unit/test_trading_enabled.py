# tests/unit/test_trading_enabled.py
"""Phase 1: trading_enabled 상태 분리 테스트."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.settings import (
    CollectorConfig, DataConfig, PaperTradingConfig,
    RiskConfig, ScreeningConfig, Settings, StrategyConfig,
)
from src.types.enums import OrderSide, SignalType
from src.types.events import SignalEvent
from src.types.models import PaperAccount, Position


def _make_settings() -> Settings:
    return Settings(
        paper_trading=PaperTradingConfig(
            initial_balance=Decimal("10000000"),
            max_position_pct=Decimal("0.25"),
            max_open_positions=4,
            fee_rate=Decimal("0.0005"),
            slippage_rate=Decimal("0.0005"),
            min_order_krw=5000,
        ),
        risk=RiskConfig(
            stop_loss_pct=Decimal("0.02"),
            take_profit_pct=Decimal("0.08"),
            trailing_stop_pct=Decimal("0.015"),
            max_daily_loss_pct=Decimal("0.05"),
            max_daily_trades=50,
            consecutive_loss_limit=5,
            cooldown_minutes=60,
        ),
        screening=ScreeningConfig(
            min_volume_krw=Decimal("500000000"),
            min_volatility_pct=Decimal("1.0"),
            max_volatility_pct=Decimal("15.0"),
            max_coins=5,
            refresh_interval_min=30,
        ),
        strategy=StrategyConfig(
            lookahead_minutes=5,
            threshold_pct=Decimal("0.3"),
            retrain_interval_hours=6,
            min_confidence=Decimal("0.6"),
        ),
        collector=CollectorConfig(
            candle_timeframe=1,
            max_candles_per_market=200,
            market_refresh_interval_min=60,
        ),
        data=DataConfig(
            db_path=":memory:",
            model_dir="data/models",
            stale_candle_days=7,
            stale_model_days=30,
            stale_order_days=90,
        ),
    )


class TestTradingEnabledOnSignal:
    """trading_enabled=False일 때 BUY 신호가 와도 주문 생성 안됨."""

    def test_signal_ignored_when_trading_disabled(self) -> None:
        from src.runtime.app import App

        settings = _make_settings()
        app = App(settings)
        app.paused = False
        app.trading_enabled = False  # 매매 비활성

        event = SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000)

        # _on_signal should return early without calling risk_manager.approve
        app.risk_manager.approve = MagicMock(return_value=(True, "OK"))  # type: ignore[method-assign]
        asyncio.get_event_loop().run_until_complete(app._on_signal(event))

        app.risk_manager.approve.assert_not_called()

    def test_signal_processed_when_trading_enabled(self) -> None:
        from src.runtime.app import App

        settings = _make_settings()
        app = App(settings)
        app.paused = False
        app.trading_enabled = True  # 매매 활성

        event = SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000)

        # Mock approve to reject so we don't need full pipeline
        app.risk_manager.approve = MagicMock(return_value=(False, "테스트 거부"))  # type: ignore[method-assign]
        asyncio.get_event_loop().run_until_complete(app._on_signal(event))

        app.risk_manager.approve.assert_called_once()


class TestTradingEnabledPositionMonitor:
    """trading_enabled=False일 때 포지션 가격 업데이트는 정상, 매도는 안됨."""

    def test_position_price_updated_when_trading_disabled(self) -> None:
        from src.runtime.app import App

        settings = _make_settings()
        app = App(settings)
        app.paused = False
        app.trading_enabled = False

        position = Position(
            market="KRW-BTC",
            side=OrderSide.BUY,
            entry_price=Decimal("50000000"),
            quantity=Decimal("0.001"),
            entry_time=1700000000,
            unrealized_pnl=Decimal("0"),
            highest_price=Decimal("50000000"),
        )
        app.account.positions["KRW-BTC"] = position

        # Mock upbit to return a price
        app.upbit.fetch_tickers = AsyncMock(return_value=[
            {"market": "KRW-BTC", "price": Decimal("48000000")},
        ])
        # Spy on execute_sell
        app.paper_engine.execute_sell = MagicMock()  # type: ignore[method-assign]

        asyncio.get_event_loop().run_until_complete(app._monitor_positions())

        # Price should be updated (unrealized_pnl changed)
        assert position.unrealized_pnl != Decimal("0")
        # But no sell should have been executed
        app.paper_engine.execute_sell.assert_not_called()
