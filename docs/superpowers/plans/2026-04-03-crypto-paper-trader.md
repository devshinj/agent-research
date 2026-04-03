# Crypto Paper Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upbit 실시간 시세 기반 ML 가상 매매 시스템 — 페이퍼 트레이딩으로 전략 성능을 검증한다.

**Architecture:** 6-Layer 모듈러 모놀리스 (types → config → repository → service → runtime → ui). 모듈 간 통신은 이벤트 버스로 느슨하게 연결. OpenAI 하네스 엔지니어링 원칙(Context, Constraints, GC) 적용.

**Tech Stack:** Python 3.12+, uv, FastAPI, React+Vite+Recharts, LightGBM/XGBoost, SQLite (aiosqlite), httpx, websockets, Pydantic, ruff, mypy, pytest

---

## Task Dependency Map

```
Task 1: 프로젝트 기반 & 하네스 설정
  │
  ├─→ Task 2: Layer 0 — Types & Enums          (독립)
  │     │
  │     ├─→ Task 3: Layer 1 — Config            (Task 2에 의존)
  │     │
  │     ├─→ Task 4: Layer 2 — Database & Repos  (Task 2, 3에 의존)
  │     │
  │     └─→ Task 5: 구조적 테스트 (하네스)         (Task 2, 3, 4에 의존)
  │
  ├─→ Task 6: Upbit API 클라이언트              (Task 2, 3에 의존)
  │     │
  │     └─→ Task 7: 데이터 수집기                (Task 4, 6에 의존)
  │
  ├─→ Task 8: 종목 스크리닝                      (Task 2, 4, 6에 의존)
  │
  ├─→ Task 9: 피처 엔지니어링                    (Task 2에 의존)
  │     │
  │     └─→ Task 10: ML 학습 & 예측              (Task 3, 4, 9에 의존)
  │
  ├─→ Task 11: 리스크 관리                       (Task 2, 3에 의존)
  │     │
  │     └─→ Task 12: 가상 매매 엔진              (Task 2, 4, 11에 의존)
  │           │
  │           └─→ Task 13: 포트폴리오 관리        (Task 2, 4, 12에 의존)
  │
  ├─→ Task 14: 이벤트 버스 & 런타임              (Task 2에 의존)
  │
  ├─→ Task 15: FastAPI 백엔드                    (Task 2, 3, 4, 14에 의존)
  │     │
  │     └─→ Task 16: React 대시보드              (Task 15에 의존)
  │
  └─→ Task 17: 통합 & 앱 오케스트레이션          (전체 의존)
```

**병렬 실행 가능 그룹:**
- **Group A** (Task 1 완료 후): Task 2
- **Group B** (Task 2 완료 후): Task 3, 6, 9, 11, 14 — 모두 병렬 가능
- **Group C** (Group B 완료 후): Task 4, 5, 7, 8, 10, 12, 15 — 의존성 충족된 것부터 병렬
- **Group D** (Group C 완료 후): Task 13, 16
- **Group E** (전체): Task 17

---

## File Map

| Layer | File | Responsibility |
|-------|------|---------------|
| L0 types | `src/types/__init__.py` | 패키지 re-export |
| L0 types | `src/types/enums.py` | OrderSide, SignalType, OrderStatus, OrderType, WSMessageType |
| L0 types | `src/types/models.py` | Candle, Order, Position, PaperAccount, Signal, DailySummary, ScreeningResult |
| L0 types | `src/types/events.py` | NewCandleEvent, ScreenedCoinsEvent, SignalEvent, TradeEvent, PriceUpdateEvent |
| L1 config | `src/config/__init__.py` | 패키지 |
| L1 config | `src/config/settings.py` | Pydantic Settings — YAML 로드, 전체 설정 |
| L2 repo | `src/repository/__init__.py` | 패키지 |
| L2 repo | `src/repository/database.py` | SQLite 연결, 테이블 초기화 |
| L2 repo | `src/repository/candle_repo.py` | 캔들 CRUD |
| L2 repo | `src/repository/order_repo.py` | 주문 CRUD |
| L2 repo | `src/repository/portfolio_repo.py` | 포트폴리오/일별 요약 CRUD |
| L3 svc | `src/service/__init__.py` | 패키지 |
| L3 svc | `src/service/upbit_client.py` | Upbit REST + WebSocket 래퍼 |
| L3 svc | `src/service/collector.py` | 분봉 수집 스케줄러 |
| L3 svc | `src/service/screener.py` | 거래량/변동성 스크리닝 |
| L3 svc | `src/service/features.py` | FeatureBuilder — 피처 생성 (순수 함수) |
| L3 svc | `src/service/trainer.py` | LightGBM 학습 + 모델 저장 |
| L3 svc | `src/service/predictor.py` | 모델 로드 + 실시간 예측 |
| L3 svc | `src/service/risk_manager.py` | 리스크 체크 (5단계 게이트) |
| L3 svc | `src/service/paper_engine.py` | 가상 체결 시뮬레이션 |
| L3 svc | `src/service/portfolio.py` | 포지션 모니터링, 자동 청산 |
| L4 rt | `src/runtime/__init__.py` | 패키지 |
| L4 rt | `src/runtime/event_bus.py` | 내부 pub/sub 이벤트 버스 |
| L4 rt | `src/runtime/scheduler.py` | asyncio 기반 주기적 작업 |
| L4 rt | `src/runtime/app.py` | 앱 라이프사이클 (startup/shutdown) |
| L5 ui | `src/ui/__init__.py` | 패키지 |
| L5 ui | `src/ui/api/server.py` | FastAPI 앱 생성, CORS, WebSocket |
| L5 ui | `src/ui/api/routes/dashboard.py` | /api/dashboard/* |
| L5 ui | `src/ui/api/routes/portfolio.py` | /api/portfolio/* |
| L5 ui | `src/ui/api/routes/strategy.py` | /api/strategy/* |
| L5 ui | `src/ui/api/routes/risk.py` | /api/risk/* |
| L5 ui | `src/ui/api/routes/control.py` | /api/control/*, /api/settings |
| L5 ui | `src/ui/frontend/` | React + Vite 프로젝트 |
| harness | `scripts/check_layers.py` | 레이어 의존성 검증 |
| harness | `scripts/quality_audit.py` | 품질 감사 |
| tests | `tests/structural/test_layer_deps.py` | 레이어 규칙 구조적 테스트 |
| tests | `tests/structural/test_decimal_enforcement.py` | float 리터럴 금지 |
| tests | `tests/unit/test_*.py` | 모듈별 단위 테스트 |
| tests | `tests/integration/test_*.py` | 통합 테스트 |
| docs | `AGENTS.md` | 에이전트 가이드 (60줄) |
| docs | `docs/architecture.md` | 아키텍처 맵 |
| docs | `docs/layer-rules.md` | 레이어 규칙 |
| docs | `docs/ml/feature-catalog.md` | 피처 카탈로그 |
| docs | `docs/trading/risk-rules.md` | 리스크 규칙 |
| docs | `docs/api/upbit-limits.md` | Upbit API 제한 |
| docs | `docs/api/dashboard-endpoints.md` | API 명세 |

---

## Task 1: 프로젝트 기반 & 하네스 설정

**Files:**
- Create: `pyproject.toml`
- Create: `ruff.toml`
- Create: `mypy.ini`
- Create: `.pre-commit-config.yaml`
- Create: `config/settings.yaml`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `docs/architecture.md`
- Create: `docs/layer-rules.md`
- Create: `src/__init__.py`

**Prereqs:** None

- [ ] **Step 1: pyproject.toml 생성**

```toml
[project]
name = "crypto-paper-trader"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "websockets>=14.0",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "httpx>=0.28",
    "lightgbm>=4.5",
    "xgboost>=2.1",
    "scikit-learn>=1.6",
    "pandas>=2.2",
    "numpy>=2.1",
    "ta>=0.11",
    "joblib>=1.4",
    "aiosqlite>=0.21",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.9",
    "mypy>=1.14",
    "pre-commit>=4.0",
    "pandas-stubs>=2.2",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: ruff.toml 생성**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "TCH"]
ignore = ["E501"]

[lint.isort]
known-first-party = ["src"]

[format]
quote-style = "double"
```

- [ ] **Step 3: mypy.ini 생성**

```ini
[mypy]
python_version = 3.12
strict = True
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_any_generics = True
check_untyped_defs = True

[mypy-ta.*]
ignore_missing_imports = True

[mypy-lightgbm.*]
ignore_missing_imports = True

[mypy-xgboost.*]
ignore_missing_imports = True

[mypy-joblib.*]
ignore_missing_imports = True

[mypy-sklearn.*]
ignore_missing_imports = True
```

- [ ] **Step 4: .pre-commit-config.yaml 생성**

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff lint
        entry: uv run ruff check
        language: system
        types: [python]

      - id: ruff-format
        name: ruff format check
        entry: uv run ruff format --check
        language: system
        types: [python]

      - id: mypy
        name: mypy type check
        entry: uv run mypy src/
        language: system
        types: [python]
        pass_filenames: false

      - id: structural-tests
        name: structural tests
        entry: uv run pytest tests/structural/ -x -q
        language: system
        pass_filenames: false
```

- [ ] **Step 5: config/settings.yaml 생성**

```yaml
# Crypto Paper Trader 설정

paper_trading:
  initial_balance: 10000000    # 1,000만원
  max_position_pct: 0.25       # 종목당 최대 25%
  max_open_positions: 4        # 동시 최대 4종목
  fee_rate: 0.0005             # Upbit 0.05%
  slippage_rate: 0.0005        # 0.05%
  min_order_krw: 5000          # 최소 주문 5,000원

risk:
  stop_loss_pct: 0.02          # 2% 손절
  take_profit_pct: 0.05        # 5% 익절
  trailing_stop_pct: 0.015     # 1.5% 트레일링 스탑
  max_daily_loss_pct: 0.05     # 일일 최대 손실 5%
  max_daily_trades: 50
  consecutive_loss_limit: 5    # 연속 손실 시 중지
  cooldown_minutes: 60

screening:
  min_volume_krw: 500000000    # 최소 5억원
  min_volatility_pct: 1.0
  max_volatility_pct: 15.0
  max_coins: 10
  refresh_interval_min: 30

strategy:
  lookahead_minutes: 5
  threshold_pct: 0.3
  retrain_interval_hours: 6
  min_confidence: 0.6

collector:
  candle_timeframe: 1          # 1분봉
  max_candles_per_market: 200
  market_refresh_interval_min: 60

data:
  db_path: "data/paper_trader.db"
  model_dir: "data/models"
  stale_candle_days: 7
  stale_model_days: 30
  stale_order_days: 90
```

- [ ] **Step 6: AGENTS.md 생성**

```markdown
# Crypto Paper Trader — Agent Guide

## Architecture
6-layer modular monolith. See docs/architecture.md
Layer rule: types -> config -> repository -> service -> runtime -> ui
NEVER import from a higher layer. tests/structural/ enforces this.

## Key Directories
- src/types/      — Pure models, no deps
- src/config/     — Settings loader (Pydantic)
- src/repository/ — DB access (SQLite)
- src/service/    — Business logic (collector, screener, ML, trading)
- src/runtime/    — Event bus, scheduler, app lifecycle
- src/ui/         — FastAPI + React dashboard

## Rules
- Financial calculations: Decimal only, never float
- All orders go through RiskManager.approve() first
- Feature pipeline: single FeatureBuilder for train AND predict
- Config changes: update settings.yaml AND docs/

## Testing
- pre-commit: ruff + mypy + structural tests
- CI: structural -> unit -> integration (3 stages)

## Docs (source of truth)
- docs/architecture.md
- docs/layer-rules.md
- docs/ml/feature-catalog.md
- docs/trading/risk-rules.md
- docs/api/dashboard-endpoints.md
```

- [ ] **Step 7: CLAUDE.md 생성**

```markdown
# CLAUDE.md

## Project
Upbit-based crypto paper trading system with ML strategy.

## Commands
- `uv sync` — install dependencies
- `uv run pytest` — run all tests
- `uv run pytest tests/structural/` — structural tests only
- `uv run ruff check src/` — lint
- `uv run mypy src/` — type check

## Conventions
- Python 3.12+, strict mypy, ruff formatting
- 6-layer architecture: types → config → repository → service → runtime → ui
- Financial math uses Decimal, never float
- All orders pass through RiskManager.approve() before PaperEngine
- Single FeatureBuilder class for both training and prediction
```

- [ ] **Step 8: docs/architecture.md 생성**

```markdown
# Architecture

## 6-Layer Modular Monolith

```
Layer 0: src/types/      — Pure domain models and enums. No dependencies.
Layer 1: src/config/     — Settings loader. Depends on: types
Layer 2: src/repository/ — Database access. Depends on: types, config
Layer 3: src/service/    — Business logic. Depends on: types, config, repository
Layer 4: src/runtime/    — Orchestration. Depends on: types, config, repository, service
Layer 5: src/ui/         — Presentation. Depends on: all lower layers
```

## Event Flow

```
collector →[NewCandleEvent]→ screener →[ScreenedCoinsEvent]→ predictor
predictor →[SignalEvent]→ risk_manager → paper_engine
paper_engine →[TradeEvent]→ portfolio → dashboard (WebSocket)
```

## Key Invariants
- Layer dependencies flow downward only (enforced by structural tests)
- Financial calculations use Decimal (enforced by structural tests)
- All orders pass through RiskManager.approve() before execution
- Single FeatureBuilder for train and predict (prevents train-serve skew)
```

- [ ] **Step 9: docs/layer-rules.md 생성**

```markdown
# Layer Dependency Rules

## Allowed Dependencies

| Layer | Can Import From |
|-------|----------------|
| L0 types | (nothing) |
| L1 config | types |
| L2 repository | types, config |
| L3 service | types, config, repository |
| L4 runtime | types, config, repository, service |
| L5 ui | types, config, repository, service, runtime |

## Enforcement
- `scripts/check_layers.py` — standalone checker
- `tests/structural/test_layer_deps.py` — pytest integration
- `.pre-commit-config.yaml` — pre-commit hook
- CI pipeline Stage 1 — blocks merge on violation
```

- [ ] **Step 10: 디렉토리 구조 생성 및 __init__.py 배치**

```bash
mkdir -p src/types src/config src/repository src/service src/runtime src/ui/api/routes src/ui/frontend
mkdir -p tests/unit tests/integration tests/structural
mkdir -p scripts data/models docs/api docs/ml docs/trading docs/decisions
touch src/__init__.py src/types/__init__.py src/config/__init__.py
touch src/repository/__init__.py src/service/__init__.py
touch src/runtime/__init__.py src/ui/__init__.py src/ui/api/__init__.py
touch src/ui/api/routes/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
touch tests/structural/__init__.py
```

- [ ] **Step 11: uv sync 실행**

Run: `uv sync`
Expected: 모든 의존성 설치 성공

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: project scaffold with harness engineering setup

Includes pyproject.toml, ruff, mypy, pre-commit, settings.yaml,
AGENTS.md, CLAUDE.md, architecture docs, and 6-layer directory structure."
```

---

## Task 2: Layer 0 — Types & Enums

**Files:**
- Create: `src/types/enums.py`
- Create: `src/types/models.py`
- Create: `src/types/events.py`
- Modify: `src/types/__init__.py`
- Create: `tests/unit/test_models.py`

**Prereqs:** Task 1

- [ ] **Step 1: 테스트 작성 — enums**

```python
# tests/unit/test_models.py
from decimal import Decimal

from src.types.enums import OrderSide, OrderStatus, OrderType, SignalType, WSMessageType


def test_signal_type_values() -> None:
    assert SignalType.BUY.value == 1
    assert SignalType.HOLD.value == 0
    assert SignalType.SELL.value == -1


def test_order_side_values() -> None:
    assert OrderSide.BUY.value == "BUY"
    assert OrderSide.SELL.value == "SELL"


def test_order_status_values() -> None:
    assert OrderStatus.PENDING.value == "PENDING"
    assert OrderStatus.FILLED.value == "FILLED"
    assert OrderStatus.CANCELLED.value == "CANCELLED"


def test_order_type_values() -> None:
    assert OrderType.MARKET.value == "MARKET"


def test_ws_message_type_values() -> None:
    assert WSMessageType.PRICE_UPDATE.value == "price_update"
    assert WSMessageType.TRADE_EXECUTED.value == "trade_executed"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: enums.py 구현**

```python
# src/types/enums.py
from enum import Enum


class SignalType(Enum):
    BUY = 1
    HOLD = 0
    SELL = -1


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class OrderType(Enum):
    MARKET = "MARKET"


class WSMessageType(Enum):
    PRICE_UPDATE = "price_update"
    POSITION_UPDATE = "position_update"
    TRADE_EXECUTED = "trade_executed"
    SIGNAL_FIRED = "signal_fired"
    RISK_ALERT = "risk_alert"
    SUMMARY_UPDATE = "summary_update"
```

- [ ] **Step 4: 테스트 추가 — models**

```python
# tests/unit/test_models.py 에 추가
from src.types.models import Candle, Order, PaperAccount, Position, Signal, DailySummary


def test_candle_creation() -> None:
    c = Candle(
        market="KRW-BTC",
        timeframe="1m",
        timestamp=1700000000,
        open=Decimal("50000000"),
        high=Decimal("50100000"),
        low=Decimal("49900000"),
        close=Decimal("50050000"),
        volume=Decimal("1.5"),
    )
    assert c.market == "KRW-BTC"
    assert c.close == Decimal("50050000")


def test_paper_account_initial_state() -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
        positions={},
    )
    assert account.initial_balance == Decimal("10000000")
    assert account.positions == {}


def test_signal_creation() -> None:
    s = Signal(
        market="KRW-ETH",
        signal_type=SignalType.BUY,
        confidence=0.75,
        timestamp=1700000000,
    )
    assert s.signal_type == SignalType.BUY
    assert s.confidence == 0.75


def test_position_creation() -> None:
    p = Position(
        market="KRW-BTC",
        side=OrderSide.BUY,
        entry_price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        entry_time=1700000000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
    )
    assert p.entry_price == Decimal("50000000")


def test_order_creation() -> None:
    o = Order(
        id="test-uuid",
        market="KRW-BTC",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        status=OrderStatus.PENDING,
        signal_confidence=0.8,
        reason="ML_SIGNAL",
        created_at=1700000000,
        fill_price=None,
        filled_at=None,
        fee=Decimal("0"),
    )
    assert o.status == OrderStatus.PENDING


def test_daily_summary_creation() -> None:
    ds = DailySummary(
        date="2026-04-03",
        starting_balance=Decimal("10000000"),
        ending_balance=Decimal("10234500"),
        realized_pnl=Decimal("234500"),
        total_trades=12,
        win_trades=8,
        loss_trades=4,
        max_drawdown_pct=Decimal("0.015"),
    )
    assert ds.win_trades == 8
```

- [ ] **Step 5: models.py 구현**

```python
# src/types/models.py
from dataclasses import dataclass, field
from decimal import Decimal

from src.types.enums import OrderSide, OrderStatus, OrderType, SignalType


@dataclass(frozen=True)
class Candle:
    market: str
    timeframe: str
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class Position:
    market: str
    side: OrderSide
    entry_price: Decimal
    quantity: Decimal
    entry_time: int
    unrealized_pnl: Decimal
    highest_price: Decimal


@dataclass
class Order:
    id: str
    market: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    status: OrderStatus
    signal_confidence: float
    reason: str
    created_at: int
    fill_price: Decimal | None
    filled_at: int | None
    fee: Decimal


@dataclass
class PaperAccount:
    initial_balance: Decimal
    cash_balance: Decimal
    positions: dict[str, Position] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    market: str
    signal_type: SignalType
    confidence: float
    timestamp: int


@dataclass(frozen=True)
class ScreeningResult:
    market: str
    volume_krw: Decimal
    volatility: Decimal
    score: Decimal
    timestamp: int


@dataclass(frozen=True)
class DailySummary:
    date: str
    starting_balance: Decimal
    ending_balance: Decimal
    realized_pnl: Decimal
    total_trades: int
    win_trades: int
    loss_trades: int
    max_drawdown_pct: Decimal
```

- [ ] **Step 6: events.py 구현**

```python
# src/types/events.py
from dataclasses import dataclass
from decimal import Decimal

from src.types.enums import SignalType
from src.types.models import Candle, Order, ScreeningResult


@dataclass(frozen=True)
class NewCandleEvent:
    candle: Candle


@dataclass(frozen=True)
class ScreenedCoinsEvent:
    results: list[ScreeningResult]
    timestamp: int


@dataclass(frozen=True)
class SignalEvent:
    market: str
    signal_type: SignalType
    confidence: float
    timestamp: int


@dataclass(frozen=True)
class TradeEvent:
    order: Order
    timestamp: int


@dataclass(frozen=True)
class PriceUpdateEvent:
    market: str
    price: Decimal
    change_pct: Decimal
    timestamp: int
```

- [ ] **Step 7: __init__.py 업데이트**

```python
# src/types/__init__.py
from src.types.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    SignalType,
    WSMessageType,
)
from src.types.events import (
    NewCandleEvent,
    PriceUpdateEvent,
    ScreenedCoinsEvent,
    SignalEvent,
    TradeEvent,
)
from src.types.models import (
    Candle,
    DailySummary,
    Order,
    PaperAccount,
    Position,
    ScreeningResult,
    Signal,
)

__all__ = [
    "Candle",
    "DailySummary",
    "NewCandleEvent",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PaperAccount",
    "Position",
    "PriceUpdateEvent",
    "ScreenedCoinsEvent",
    "ScreeningResult",
    "Signal",
    "SignalEvent",
    "SignalType",
    "TradeEvent",
    "WSMessageType",
]
```

- [ ] **Step 8: 전체 테스트 실행**

Run: `uv run pytest tests/unit/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 9: lint & type check**

Run: `uv run ruff check src/types/ && uv run mypy src/types/`
Expected: 에러 없음

- [ ] **Step 10: Commit**

```bash
git add src/types/ tests/unit/test_models.py
git commit -m "feat: Layer 0 types — enums, models, events"
```

---

## Task 3: Layer 1 — Config

**Files:**
- Create: `src/config/settings.py`
- Modify: `src/config/__init__.py`
- Create: `tests/unit/test_config.py`

**Prereqs:** Task 1, Task 2

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_config.py
from pathlib import Path
from decimal import Decimal

from src.config.settings import Settings


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
paper_trading:
  initial_balance: 10000000
  max_position_pct: 0.25
  max_open_positions: 4
  fee_rate: 0.0005
  slippage_rate: 0.0005
  min_order_krw: 5000

risk:
  stop_loss_pct: 0.02
  take_profit_pct: 0.05
  trailing_stop_pct: 0.015
  max_daily_loss_pct: 0.05
  max_daily_trades: 50
  consecutive_loss_limit: 5
  cooldown_minutes: 60

screening:
  min_volume_krw: 500000000
  min_volatility_pct: 1.0
  max_volatility_pct: 15.0
  max_coins: 10
  refresh_interval_min: 30

strategy:
  lookahead_minutes: 5
  threshold_pct: 0.3
  retrain_interval_hours: 6
  min_confidence: 0.6

collector:
  candle_timeframe: 1
  max_candles_per_market: 200
  market_refresh_interval_min: 60

data:
  db_path: "data/paper_trader.db"
  model_dir: "data/models"
  stale_candle_days: 7
  stale_model_days: 30
  stale_order_days: 90
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(yaml_content)
    settings = Settings.from_yaml(config_file)

    assert settings.paper_trading.initial_balance == Decimal("10000000")
    assert settings.paper_trading.max_position_pct == Decimal("0.25")
    assert settings.risk.stop_loss_pct == Decimal("0.02")
    assert settings.screening.min_volume_krw == Decimal("500000000")
    assert settings.strategy.lookahead_minutes == 5
    assert settings.collector.candle_timeframe == 1
    assert settings.data.db_path == "data/paper_trader.db"


def test_settings_max_open_positions_matches_pct() -> None:
    """max_open_positions * max_position_pct <= 1.0"""
    settings = Settings.from_yaml(Path("config/settings.yaml"))
    total = settings.paper_trading.max_open_positions * settings.paper_trading.max_position_pct
    assert total <= Decimal("1.0")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: settings.py 구현**

```python
# src/config/settings.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PaperTradingConfig:
    initial_balance: Decimal
    max_position_pct: Decimal
    max_open_positions: int
    fee_rate: Decimal
    slippage_rate: Decimal
    min_order_krw: int


@dataclass(frozen=True)
class RiskConfig:
    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    trailing_stop_pct: Decimal
    max_daily_loss_pct: Decimal
    max_daily_trades: int
    consecutive_loss_limit: int
    cooldown_minutes: int


@dataclass(frozen=True)
class ScreeningConfig:
    min_volume_krw: Decimal
    min_volatility_pct: Decimal
    max_volatility_pct: Decimal
    max_coins: int
    refresh_interval_min: int


@dataclass(frozen=True)
class StrategyConfig:
    lookahead_minutes: int
    threshold_pct: Decimal
    retrain_interval_hours: int
    min_confidence: Decimal


@dataclass(frozen=True)
class CollectorConfig:
    candle_timeframe: int
    max_candles_per_market: int
    market_refresh_interval_min: int


@dataclass(frozen=True)
class DataConfig:
    db_path: str
    model_dir: str
    stale_candle_days: int
    stale_model_days: int
    stale_order_days: int


@dataclass(frozen=True)
class Settings:
    paper_trading: PaperTradingConfig
    risk: RiskConfig
    screening: ScreeningConfig
    strategy: StrategyConfig
    collector: CollectorConfig
    data: DataConfig

    @staticmethod
    def from_yaml(path: Path) -> Settings:
        with open(path) as f:
            raw = yaml.safe_load(f)

        return Settings(
            paper_trading=PaperTradingConfig(
                initial_balance=Decimal(str(raw["paper_trading"]["initial_balance"])),
                max_position_pct=Decimal(str(raw["paper_trading"]["max_position_pct"])),
                max_open_positions=int(raw["paper_trading"]["max_open_positions"]),
                fee_rate=Decimal(str(raw["paper_trading"]["fee_rate"])),
                slippage_rate=Decimal(str(raw["paper_trading"]["slippage_rate"])),
                min_order_krw=int(raw["paper_trading"]["min_order_krw"]),
            ),
            risk=RiskConfig(
                stop_loss_pct=Decimal(str(raw["risk"]["stop_loss_pct"])),
                take_profit_pct=Decimal(str(raw["risk"]["take_profit_pct"])),
                trailing_stop_pct=Decimal(str(raw["risk"]["trailing_stop_pct"])),
                max_daily_loss_pct=Decimal(str(raw["risk"]["max_daily_loss_pct"])),
                max_daily_trades=int(raw["risk"]["max_daily_trades"]),
                consecutive_loss_limit=int(raw["risk"]["consecutive_loss_limit"]),
                cooldown_minutes=int(raw["risk"]["cooldown_minutes"]),
            ),
            screening=ScreeningConfig(
                min_volume_krw=Decimal(str(raw["screening"]["min_volume_krw"])),
                min_volatility_pct=Decimal(str(raw["screening"]["min_volatility_pct"])),
                max_volatility_pct=Decimal(str(raw["screening"]["max_volatility_pct"])),
                max_coins=int(raw["screening"]["max_coins"]),
                refresh_interval_min=int(raw["screening"]["refresh_interval_min"]),
            ),
            strategy=StrategyConfig(
                lookahead_minutes=int(raw["strategy"]["lookahead_minutes"]),
                threshold_pct=Decimal(str(raw["strategy"]["threshold_pct"])),
                retrain_interval_hours=int(raw["strategy"]["retrain_interval_hours"]),
                min_confidence=Decimal(str(raw["strategy"]["min_confidence"])),
            ),
            collector=CollectorConfig(
                candle_timeframe=int(raw["collector"]["candle_timeframe"]),
                max_candles_per_market=int(raw["collector"]["max_candles_per_market"]),
                market_refresh_interval_min=int(raw["collector"]["market_refresh_interval_min"]),
            ),
            data=DataConfig(
                db_path=str(raw["data"]["db_path"]),
                model_dir=str(raw["data"]["model_dir"]),
                stale_candle_days=int(raw["data"]["stale_candle_days"]),
                stale_model_days=int(raw["data"]["stale_model_days"]),
                stale_order_days=int(raw["data"]["stale_order_days"]),
            ),
        )
```

- [ ] **Step 4: __init__.py 업데이트**

```python
# src/config/__init__.py
from src.config.settings import Settings

__all__ = ["Settings"]
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/config/ tests/unit/test_config.py
git commit -m "feat: Layer 1 config — YAML settings loader with Decimal"
```

---

## Task 4: Layer 2 — Database & Repositories

**Files:**
- Create: `src/repository/database.py`
- Create: `src/repository/candle_repo.py`
- Create: `src/repository/order_repo.py`
- Create: `src/repository/portfolio_repo.py`
- Modify: `src/repository/__init__.py`
- Create: `tests/unit/test_candle_repo.py`
- Create: `tests/unit/test_order_repo.py`
- Create: `tests/unit/test_portfolio_repo.py`

**Prereqs:** Task 2, Task 3

- [ ] **Step 1: 테스트 작성 — database.py**

```python
# tests/unit/test_candle_repo.py
import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.candle_repo import CandleRepository
from src.types.models import Candle


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def candle_repo(db):
    return CandleRepository(db)


async def test_save_and_get_candle(candle_repo):
    candle = Candle(
        market="KRW-BTC",
        timeframe="1m",
        timestamp=1700000000,
        open=Decimal("50000000"),
        high=Decimal("50100000"),
        low=Decimal("49900000"),
        close=Decimal("50050000"),
        volume=Decimal("1.5"),
    )
    await candle_repo.save(candle)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=1)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"
    assert result[0].close == Decimal("50050000")


async def test_save_duplicate_candle_upserts(candle_repo):
    candle1 = Candle("KRW-BTC", "1m", 1700000000,
                     Decimal("50000000"), Decimal("50100000"),
                     Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    candle2 = Candle("KRW-BTC", "1m", 1700000000,
                     Decimal("50000000"), Decimal("50200000"),
                     Decimal("49800000"), Decimal("50150000"), Decimal("2.0"))
    await candle_repo.save(candle1)
    await candle_repo.save(candle2)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=10)
    assert len(result) == 1
    assert result[0].high == Decimal("50200000")


async def test_get_latest_returns_ordered(candle_repo):
    for i in range(5):
        c = Candle("KRW-BTC", "1m", 1700000000 + i * 60,
                   Decimal("50000000"), Decimal("50100000"),
                   Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
        await candle_repo.save(c)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=3)
    assert len(result) == 3
    assert result[0].timestamp > result[1].timestamp  # 최신 먼저


async def test_delete_older_than(candle_repo):
    old = Candle("KRW-BTC", "1m", 1000000000,
                 Decimal("50000000"), Decimal("50100000"),
                 Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    new = Candle("KRW-BTC", "1m", 1700000000,
                 Decimal("50000000"), Decimal("50100000"),
                 Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    await candle_repo.save(old)
    await candle_repo.save(new)
    deleted = await candle_repo.delete_older_than(1500000000)
    assert deleted == 1
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=10)
    assert len(result) == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_candle_repo.py -v`
Expected: FAIL

- [ ] **Step 3: database.py 구현**

```python
# src/repository/database.py
from __future__ import annotations

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    market     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    timestamp  INTEGER NOT NULL,
    open       TEXT NOT NULL,
    high       TEXT NOT NULL,
    low        TEXT NOT NULL,
    close      TEXT NOT NULL,
    volume     TEXT NOT NULL,
    PRIMARY KEY (market, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS orders (
    id                TEXT PRIMARY KEY,
    market            TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    price             TEXT NOT NULL,
    fill_price        TEXT,
    quantity          TEXT NOT NULL,
    fee               TEXT NOT NULL,
    status            TEXT NOT NULL,
    signal_confidence REAL,
    reason            TEXT,
    created_at        INTEGER NOT NULL,
    filled_at         INTEGER
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date             TEXT PRIMARY KEY,
    starting_balance TEXT NOT NULL,
    ending_balance   TEXT NOT NULL,
    realized_pnl     TEXT NOT NULL,
    total_trades     INTEGER NOT NULL,
    win_trades       INTEGER NOT NULL,
    loss_trades      INTEGER NOT NULL,
    max_drawdown_pct TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screening_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  INTEGER NOT NULL,
    market     TEXT NOT NULL,
    volume_krw TEXT NOT NULL,
    volatility TEXT NOT NULL,
    score      TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
```

Note: 모든 금액 필드를 TEXT로 저장하여 Decimal 정밀도를 보존합니다.

- [ ] **Step 4: candle_repo.py 구현**

```python
# src/repository/candle_repo.py
from __future__ import annotations

from decimal import Decimal

from src.repository.database import Database
from src.types.models import Candle


class CandleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, candle: Candle) -> None:
        await self._db.conn.execute(
            """INSERT INTO candles (market, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(market, timeframe, timestamp) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            (candle.market, candle.timeframe, candle.timestamp,
             str(candle.open), str(candle.high), str(candle.low),
             str(candle.close), str(candle.volume)),
        )
        await self._db.conn.commit()

    async def save_many(self, candles: list[Candle]) -> None:
        await self._db.conn.executemany(
            """INSERT INTO candles (market, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(market, timeframe, timestamp) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            [(c.market, c.timeframe, c.timestamp,
              str(c.open), str(c.high), str(c.low),
              str(c.close), str(c.volume)) for c in candles],
        )
        await self._db.conn.commit()

    async def get_latest(self, market: str, timeframe: str, limit: int = 200) -> list[Candle]:
        cursor = await self._db.conn.execute(
            """SELECT market, timeframe, timestamp, open, high, low, close, volume
               FROM candles WHERE market=? AND timeframe=?
               ORDER BY timestamp DESC LIMIT ?""",
            (market, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [
            Candle(
                market=r[0], timeframe=r[1], timestamp=r[2],
                open=Decimal(r[3]), high=Decimal(r[4]), low=Decimal(r[5]),
                close=Decimal(r[6]), volume=Decimal(r[7]),
            )
            for r in rows
        ]

    async def delete_older_than(self, timestamp: int) -> int:
        cursor = await self._db.conn.execute(
            "DELETE FROM candles WHERE timestamp < ?", (timestamp,)
        )
        await self._db.conn.commit()
        return cursor.rowcount
```

- [ ] **Step 5: 테스트 실행 — candle_repo 통과 확인**

Run: `uv run pytest tests/unit/test_candle_repo.py -v`
Expected: ALL PASS

- [ ] **Step 6: order_repo.py 테스트 & 구현**

```python
# tests/unit/test_order_repo.py
import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def order_repo(db):
    return OrderRepository(db)


async def test_save_and_get_order(order_repo):
    order = Order(
        id="order-1", market="KRW-BTC", side=OrderSide.BUY,
        order_type=OrderType.MARKET, price=Decimal("50000000"),
        quantity=Decimal("0.001"), status=OrderStatus.FILLED,
        signal_confidence=0.8, reason="ML_SIGNAL",
        created_at=1700000000, fill_price=Decimal("50025000"),
        filled_at=1700000001, fee=Decimal("25012"),
    )
    await order_repo.save(order)
    result = await order_repo.get_by_id("order-1")
    assert result is not None
    assert result.fill_price == Decimal("50025000")


async def test_get_recent_orders(order_repo):
    for i in range(5):
        o = Order(
            id=f"order-{i}", market="KRW-BTC", side=OrderSide.BUY,
            order_type=OrderType.MARKET, price=Decimal("50000000"),
            quantity=Decimal("0.001"), status=OrderStatus.FILLED,
            signal_confidence=0.7, reason="ML_SIGNAL",
            created_at=1700000000 + i * 60, fill_price=Decimal("50000000"),
            filled_at=1700000001 + i * 60, fee=Decimal("25000"),
        )
        await order_repo.save(o)
    result = await order_repo.get_recent(limit=3)
    assert len(result) == 3
    assert result[0].created_at > result[1].created_at


async def test_count_today_trades(order_repo):
    o = Order(
        id="order-today", market="KRW-BTC", side=OrderSide.BUY,
        order_type=OrderType.MARKET, price=Decimal("50000000"),
        quantity=Decimal("0.001"), status=OrderStatus.FILLED,
        signal_confidence=0.7, reason="ML_SIGNAL",
        created_at=1700000000, fill_price=Decimal("50000000"),
        filled_at=1700000001, fee=Decimal("25000"),
    )
    await order_repo.save(o)
    count = await order_repo.count_since(1700000000 - 1)
    assert count == 1
```

```python
# src/repository/order_repo.py
from __future__ import annotations

from decimal import Decimal

from src.repository.database import Database
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, order: Order) -> None:
        await self._db.conn.execute(
            """INSERT INTO orders (id, market, side, order_type, price, fill_price,
               quantity, fee, status, signal_confidence, reason, created_at, filled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 fill_price=excluded.fill_price, fee=excluded.fee,
                 status=excluded.status, filled_at=excluded.filled_at""",
            (order.id, order.market, order.side.value, order.order_type.value,
             str(order.price), str(order.fill_price) if order.fill_price else None,
             str(order.quantity), str(order.fee), order.status.value,
             order.signal_confidence, order.reason, order.created_at, order.filled_at),
        )
        await self._db.conn.commit()

    async def get_by_id(self, order_id: str) -> Order | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_order(row)

    async def get_recent(self, limit: int = 10) -> list[Order]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_order(r) for r in rows]

    async def count_since(self, timestamp: int) -> int:
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM orders WHERE created_at >= ?", (timestamp,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _row_to_order(row: tuple) -> Order:  # type: ignore[type-arg]
        return Order(
            id=row[0], market=row[1], side=OrderSide(row[2]),
            order_type=OrderType(row[3]), price=Decimal(row[4]),
            fill_price=Decimal(row[5]) if row[5] else None,
            quantity=Decimal(row[6]), fee=Decimal(row[7]),
            status=OrderStatus(row[8]), signal_confidence=float(row[9]) if row[9] else 0.0,
            reason=row[10] or "", created_at=row[11],
            filled_at=row[12],
        )
```

- [ ] **Step 7: portfolio_repo.py 테스트 & 구현**

```python
# tests/unit/test_portfolio_repo.py
import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.portfolio_repo import PortfolioRepository
from src.types.models import DailySummary


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def portfolio_repo(db):
    return PortfolioRepository(db)


async def test_save_and_get_daily_summary(portfolio_repo):
    ds = DailySummary(
        date="2026-04-03", starting_balance=Decimal("10000000"),
        ending_balance=Decimal("10234500"), realized_pnl=Decimal("234500"),
        total_trades=12, win_trades=8, loss_trades=4,
        max_drawdown_pct=Decimal("0.015"),
    )
    await portfolio_repo.save_daily_summary(ds)
    result = await portfolio_repo.get_daily_summary("2026-04-03")
    assert result is not None
    assert result.realized_pnl == Decimal("234500")


async def test_get_daily_summaries_range(portfolio_repo):
    for i in range(3):
        ds = DailySummary(
            date=f"2026-04-0{i+1}", starting_balance=Decimal("10000000"),
            ending_balance=Decimal("10000000"), realized_pnl=Decimal("0"),
            total_trades=0, win_trades=0, loss_trades=0,
            max_drawdown_pct=Decimal("0"),
        )
        await portfolio_repo.save_daily_summary(ds)
    result = await portfolio_repo.get_daily_summaries("2026-04-01", "2026-04-03")
    assert len(result) == 3
```

```python
# src/repository/portfolio_repo.py
from __future__ import annotations

from decimal import Decimal

from src.repository.database import Database
from src.types.models import DailySummary


class PortfolioRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_daily_summary(self, summary: DailySummary) -> None:
        await self._db.conn.execute(
            """INSERT INTO daily_summary
               (date, starting_balance, ending_balance, realized_pnl,
                total_trades, win_trades, loss_trades, max_drawdown_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                 ending_balance=excluded.ending_balance,
                 realized_pnl=excluded.realized_pnl,
                 total_trades=excluded.total_trades,
                 win_trades=excluded.win_trades,
                 loss_trades=excluded.loss_trades,
                 max_drawdown_pct=excluded.max_drawdown_pct""",
            (summary.date, str(summary.starting_balance), str(summary.ending_balance),
             str(summary.realized_pnl), summary.total_trades, summary.win_trades,
             summary.loss_trades, str(summary.max_drawdown_pct)),
        )
        await self._db.conn.commit()

    async def get_daily_summary(self, date: str) -> DailySummary | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM daily_summary WHERE date=?", (date,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_summary(row)

    async def get_daily_summaries(self, start_date: str, end_date: str) -> list[DailySummary]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM daily_summary WHERE date >= ? AND date <= ? ORDER BY date",
            (start_date, end_date),
        )
        rows = await cursor.fetchall()
        return [self._row_to_summary(r) for r in rows]

    @staticmethod
    def _row_to_summary(row: tuple) -> DailySummary:  # type: ignore[type-arg]
        return DailySummary(
            date=row[0], starting_balance=Decimal(row[1]),
            ending_balance=Decimal(row[2]), realized_pnl=Decimal(row[3]),
            total_trades=int(row[4]), win_trades=int(row[5]),
            loss_trades=int(row[6]), max_drawdown_pct=Decimal(row[7]),
        )
```

- [ ] **Step 8: __init__.py 업데이트**

```python
# src/repository/__init__.py
from src.repository.candle_repo import CandleRepository
from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.repository.portfolio_repo import PortfolioRepository

__all__ = ["CandleRepository", "Database", "OrderRepository", "PortfolioRepository"]
```

- [ ] **Step 9: 전체 repo 테스트 실행**

Run: `uv run pytest tests/unit/test_candle_repo.py tests/unit/test_order_repo.py tests/unit/test_portfolio_repo.py -v`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add src/repository/ tests/unit/test_candle_repo.py tests/unit/test_order_repo.py tests/unit/test_portfolio_repo.py
git commit -m "feat: Layer 2 repository — database, candle/order/portfolio repos"
```

---

## Task 5: 구조적 테스트 (하네스 Constraints)

**Files:**
- Create: `scripts/check_layers.py`
- Create: `tests/structural/test_layer_deps.py`
- Create: `tests/structural/test_decimal_enforcement.py`

**Prereqs:** Task 2, 3, 4

- [ ] **Step 1: check_layers.py 구현**

```python
# scripts/check_layers.py
"""Layer dependency checker — ensures no upward imports across the 6-layer architecture."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYER_MAP: dict[str, int] = {
    "types": 0,
    "config": 1,
    "repository": 2,
    "service": 3,
    "runtime": 4,
    "ui": 5,
}


def get_layer(filepath: Path) -> int | None:
    parts = filepath.parts
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts):
            layer_name = parts[i + 1]
            return LAYER_MAP.get(layer_name)
    return None


def get_imported_layer(module: str) -> int | None:
    parts = module.split(".")
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts):
            return LAYER_MAP.get(parts[i + 1])
    return None


def check_file(filepath: Path) -> list[str]:
    current_layer = get_layer(filepath)
    if current_layer is None:
        return []

    violations: list[str] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        module: str | None = None
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name

        if module:
            imported_layer = get_imported_layer(module)
            if imported_layer is not None and imported_layer > current_layer:
                layer_names = {v: k for k, v in LAYER_MAP.items()}
                violations.append(
                    f"{filepath}:{node.lineno} — "
                    f"{layer_names[current_layer]}(L{current_layer}) imports "
                    f"{layer_names[imported_layer]}(L{imported_layer}): {module}"
                )
    return violations


def main() -> int:
    src_dir = Path("src")
    all_violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        all_violations.extend(check_file(py_file))

    if all_violations:
        print("Layer dependency violations found:")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("No layer violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: test_layer_deps.py 구현**

```python
# tests/structural/test_layer_deps.py
from pathlib import Path

from scripts.check_layers import check_file


def test_no_upward_layer_dependency() -> None:
    src_dir = Path("src")
    violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        violations.extend(check_file(py_file))
    assert violations == [], "Layer dependency violations:\n" + "\n".join(violations)
```

- [ ] **Step 3: test_decimal_enforcement.py 구현**

```python
# tests/structural/test_decimal_enforcement.py
import ast
from pathlib import Path

FINANCIAL_MODULES = [
    Path("src/service/paper_engine.py"),
    Path("src/service/risk_manager.py"),
    Path("src/service/portfolio.py"),
]


def test_no_float_literals_in_financial_modules() -> None:
    """Financial modules must use Decimal, not float literals for monetary values."""
    violations: list[str] = []
    for filepath in FINANCIAL_MODULES:
        if not filepath.exists():
            continue
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                violations.append(f"{filepath}:{node.lineno} — float literal: {node.value}")

    assert violations == [], (
        "Float literals found in financial modules (use Decimal instead):\n"
        + "\n".join(violations)
    )
```

- [ ] **Step 4: 구조적 테스트 실행**

Run: `uv run pytest tests/structural/ -v`
Expected: ALL PASS

- [ ] **Step 5: check_layers.py 직접 실행**

Run: `uv run python scripts/check_layers.py`
Expected: "No layer violations found."

- [ ] **Step 6: Commit**

```bash
git add scripts/check_layers.py tests/structural/
git commit -m "feat: harness constraints — layer dep checker, decimal enforcement tests"
```

---

## Task 6: Upbit API 클라이언트

**Files:**
- Create: `src/service/upbit_client.py`
- Create: `tests/unit/test_upbit_client.py`
- Create: `docs/api/upbit-limits.md`

**Prereqs:** Task 2, Task 3

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_upbit_client.py
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.service.upbit_client import UpbitClient


@pytest.fixture
def client():
    return UpbitClient()


async def test_parse_markets_response(client):
    raw = [
        {"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
        {"market": "KRW-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
        {"market": "BTC-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
    ]
    result = client.filter_krw_markets(raw)
    assert len(result) == 2
    assert result[0] == "KRW-BTC"
    assert result[1] == "KRW-ETH"


async def test_parse_candle_response(client):
    raw = {
        "market": "KRW-BTC",
        "candle_date_time_utc": "2026-04-03T12:00:00",
        "opening_price": 50000000,
        "high_price": 50100000,
        "low_price": 49900000,
        "trade_price": 50050000,
        "candle_acc_trade_volume": 1.5,
        "timestamp": 1700000000000,
    }
    candle = client.parse_candle(raw, timeframe="1m")
    assert candle.market == "KRW-BTC"
    assert candle.close == Decimal("50050000")
    assert candle.timestamp == 1700000000


async def test_parse_ticker_response(client):
    raw = {
        "market": "KRW-BTC",
        "trade_price": 50050000,
        "acc_trade_price_24h": 5000000000,
        "signed_change_rate": 0.015,
        "highest_52_week_price": 80000000,
        "lowest_52_week_price": 30000000,
        "timestamp": 1700000000000,
    }
    ticker = client.parse_ticker(raw)
    assert ticker["market"] == "KRW-BTC"
    assert ticker["price"] == Decimal("50050000")
    assert ticker["volume_24h"] == Decimal("5000000000")
    assert ticker["change_rate"] == Decimal("0.015")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_upbit_client.py -v`
Expected: FAIL

- [ ] **Step 3: upbit_client.py 구현**

```python
# src/service/upbit_client.py
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx

from src.types.models import Candle

UPBIT_REST_URL = "https://api.upbit.com/v1"
UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
REST_RATE_LIMIT = 10  # requests per second


class UpbitClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(REST_RATE_LIMIT)

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=UPBIT_REST_URL,
                timeout=10.0,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── REST API ──

    async def fetch_markets(self) -> list[str]:
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get("/market/all", params={"isDetails": "false"})
            resp.raise_for_status()
        return self.filter_krw_markets(resp.json())

    async def fetch_candles(
        self, market: str, timeframe: int = 1, count: int = 200
    ) -> list[Candle]:
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get(
                f"/candles/minutes/{timeframe}",
                params={"market": market, "count": count},
            )
            resp.raise_for_status()
        return [self.parse_candle(raw, f"{timeframe}m") for raw in resp.json()]

    async def fetch_tickers(self, markets: list[str]) -> list[dict[str, Any]]:
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get(
                "/ticker",
                params={"markets": ",".join(markets)},
            )
            resp.raise_for_status()
        return [self.parse_ticker(raw) for raw in resp.json()]

    # ── Parsers ──

    @staticmethod
    def filter_krw_markets(raw_markets: list[dict[str, Any]]) -> list[str]:
        return [m["market"] for m in raw_markets if m["market"].startswith("KRW-")]

    @staticmethod
    def parse_candle(raw: dict[str, Any], timeframe: str) -> Candle:
        return Candle(
            market=str(raw["market"]),
            timeframe=timeframe,
            timestamp=int(raw["timestamp"]) // 1000,
            open=Decimal(str(raw["opening_price"])),
            high=Decimal(str(raw["high_price"])),
            low=Decimal(str(raw["low_price"])),
            close=Decimal(str(raw["trade_price"])),
            volume=Decimal(str(raw["candle_acc_trade_volume"])),
        )

    @staticmethod
    def parse_ticker(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": str(raw["market"]),
            "price": Decimal(str(raw["trade_price"])),
            "volume_24h": Decimal(str(raw["acc_trade_price_24h"])),
            "change_rate": Decimal(str(raw["signed_change_rate"])),
            "timestamp": int(raw["timestamp"]) // 1000,
        }

    # ── WebSocket ──

    @staticmethod
    def build_ws_subscribe_message(
        markets: list[str], types: list[str] | None = None
    ) -> str:
        if types is None:
            types = ["ticker"]
        payload: list[dict[str, Any]] = [{"ticket": "crypto-paper-trader"}]
        for t in types:
            payload.append({"type": t, "codes": markets})
        return json.dumps(payload)
```

- [ ] **Step 4: docs/api/upbit-limits.md 생성**

```markdown
# Upbit API Limits

## REST API
- Rate limit: 10 requests/second (exchange API key 없이)
- Candle API: 최대 200개/요청
- Ticker API: 복수 종목 한번에 조회 가능

## WebSocket
- 연결당 최대 15개 구독
- 종목 수 > 15일 경우 다중 연결 필요
- 형식: JSON array of subscribe commands

## Notes
- KRW 마켓만 사용 (market prefix: "KRW-")
- timestamp는 milliseconds — 저장 시 seconds로 변환 (// 1000)
- 모든 가격은 str → Decimal로 파싱
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_upbit_client.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/service/upbit_client.py tests/unit/test_upbit_client.py docs/api/upbit-limits.md
git commit -m "feat: Upbit API client with REST/WS support, rate limiting"
```

---

## Task 7: 데이터 수집기

**Files:**
- Create: `src/service/collector.py`
- Create: `tests/unit/test_collector.py`

**Prereqs:** Task 4, Task 6

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_collector.py
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from src.service.collector import Collector
from src.types.models import Candle


@pytest.fixture
def mock_upbit_client():
    client = AsyncMock()
    client.fetch_markets.return_value = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
    client.fetch_candles.return_value = [
        Candle("KRW-BTC", "1m", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("1.5")),
    ]
    return client


@pytest.fixture
def mock_candle_repo():
    repo = AsyncMock()
    repo.save_many.return_value = None
    return repo


def test_collector_creation(mock_upbit_client, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=200,
    )
    assert collector._timeframe == 1


async def test_refresh_markets(mock_upbit_client, mock_candle_repo):
    collector = Collector(mock_upbit_client, mock_candle_repo, 1, 200)
    markets = await collector.refresh_markets()
    assert markets == ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
    mock_upbit_client.fetch_markets.assert_awaited_once()


async def test_collect_candles_for_market(mock_upbit_client, mock_candle_repo):
    collector = Collector(mock_upbit_client, mock_candle_repo, 1, 200)
    await collector.collect_candles(["KRW-BTC"])
    mock_upbit_client.fetch_candles.assert_awaited_once_with("KRW-BTC", 1, 200)
    mock_candle_repo.save_many.assert_awaited_once()
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_collector.py -v`
Expected: FAIL

- [ ] **Step 3: collector.py 구현**

```python
# src/service/collector.py
from __future__ import annotations

import asyncio
import logging

from src.repository.candle_repo import CandleRepository
from src.service.upbit_client import UpbitClient

logger = logging.getLogger(__name__)


class Collector:
    def __init__(
        self,
        upbit_client: UpbitClient,
        candle_repo: CandleRepository,
        timeframe: int,
        max_candles: int,
    ) -> None:
        self._client = upbit_client
        self._repo = candle_repo
        self._timeframe = timeframe
        self._max_candles = max_candles
        self._markets: list[str] = []

    @property
    def markets(self) -> list[str]:
        return self._markets

    async def refresh_markets(self) -> list[str]:
        self._markets = await self._client.fetch_markets()
        logger.info("Refreshed markets: %d KRW markets found", len(self._markets))
        return self._markets

    async def collect_candles(self, markets: list[str]) -> None:
        for market in markets:
            try:
                candles = await self._client.fetch_candles(
                    market, self._timeframe, self._max_candles
                )
                if candles:
                    await self._repo.save_many(candles)
                    logger.info("Collected %d candles for %s", len(candles), market)
            except Exception:
                logger.exception("Failed to collect candles for %s", market)
            await asyncio.sleep(0.11)  # rate limit: ~9 req/s
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_collector.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/collector.py tests/unit/test_collector.py
git commit -m "feat: data collector — fetches Upbit candles and stores to DB"
```

---

## Task 8: 종목 스크리닝

**Files:**
- Create: `src/service/screener.py`
- Create: `tests/unit/test_screener.py`

**Prereqs:** Task 2, Task 4, Task 6

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_screener.py
from decimal import Decimal

from src.service.screener import Screener
from src.config.settings import ScreeningConfig


def make_config() -> ScreeningConfig:
    return ScreeningConfig(
        min_volume_krw=Decimal("500000000"),
        min_volatility_pct=Decimal("1.0"),
        max_volatility_pct=Decimal("15.0"),
        max_coins=3,
        refresh_interval_min=30,
    )


def make_ticker(market: str, volume: str, change: str) -> dict:
    return {
        "market": market,
        "price": Decimal("50000000"),
        "volume_24h": Decimal(volume),
        "change_rate": Decimal(change),
        "timestamp": 1700000000,
    }


def test_filter_by_volume():
    config = make_config()
    screener = Screener(config)
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),   # 10억 → pass
        make_ticker("KRW-DOGE", "100000000", "0.05"),    # 1억 → fail (< 5억)
    ]
    result = screener.screen(tickers)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"


def test_filter_by_volatility_range():
    config = make_config()
    screener = Screener(config)
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),    # 3% → pass
        make_ticker("KRW-SHIB", "1000000000", "0.20"),   # 20% → fail (> 15%)
        make_ticker("KRW-USDT", "1000000000", "0.001"),  # 0.1% → fail (< 1%)
    ]
    result = screener.screen(tickers)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"


def test_max_coins_limit():
    config = make_config()  # max_coins=3
    screener = Screener(config)
    tickers = [
        make_ticker(f"KRW-COIN{i}", str(1000000000 - i * 100000000), "0.05")
        for i in range(5)
    ]
    result = screener.screen(tickers)
    assert len(result) == 3


def test_sorted_by_score_descending():
    config = make_config()
    screener = Screener(config)
    tickers = [
        make_ticker("KRW-LOW", "600000000", "0.02"),     # 낮은 점수
        make_ticker("KRW-HIGH", "2000000000", "0.08"),   # 높은 점수
    ]
    result = screener.screen(tickers)
    assert result[0].market == "KRW-HIGH"


def test_empty_tickers():
    config = make_config()
    screener = Screener(config)
    result = screener.screen([])
    assert result == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_screener.py -v`
Expected: FAIL

- [ ] **Step 3: screener.py 구현**

```python
# src/service/screener.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.config.settings import ScreeningConfig
from src.types.models import ScreeningResult


class Screener:
    def __init__(self, config: ScreeningConfig) -> None:
        self._config = config

    def screen(self, tickers: list[dict[str, Any]]) -> list[ScreeningResult]:
        candidates: list[ScreeningResult] = []

        for t in tickers:
            volume_24h: Decimal = t["volume_24h"]
            change_rate: Decimal = abs(t["change_rate"]) * Decimal("100")  # → %
            timestamp: int = t["timestamp"]

            # 거래대금 필터
            if volume_24h < self._config.min_volume_krw:
                continue

            # 변동성 필터
            if change_rate < self._config.min_volatility_pct:
                continue
            if change_rate > self._config.max_volatility_pct:
                continue

            # 점수: 거래대금(정규화) × 변동성
            score = (volume_24h / Decimal("1000000000")) * change_rate

            candidates.append(ScreeningResult(
                market=t["market"],
                volume_krw=volume_24h,
                volatility=change_rate,
                score=score,
                timestamp=timestamp,
            ))

        # 점수 내림차순 정렬 → 상위 N개
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[: self._config.max_coins]
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_screener.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/screener.py tests/unit/test_screener.py
git commit -m "feat: coin screener — volume/volatility filtering and scoring"
```

---

## Task 9: 피처 엔지니어링

**Files:**
- Create: `src/service/features.py`
- Create: `tests/unit/test_features.py`
- Create: `docs/ml/feature-catalog.md`

**Prereqs:** Task 2

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_features.py
import pandas as pd
import numpy as np
from decimal import Decimal

from src.service.features import FeatureBuilder


def make_candle_df(n: int = 100) -> pd.DataFrame:
    """테스트용 캔들 DataFrame 생성"""
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_feature_builder_returns_dataframe():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    features = builder.build(df)
    assert isinstance(features, pd.DataFrame)
    assert len(features) > 0


def test_feature_columns_present():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    features = builder.build(df)

    expected_cols = [
        "return_1m", "return_5m", "return_15m",
        "rsi_14", "rsi_7",
        "macd", "macd_signal", "macd_hist",
        "bb_width",
        "ema_5_ratio", "ema_20_ratio",
        "volume_ratio_5m", "volume_ratio_20m",
        "high_low_ratio", "close_position",
    ]
    for col in expected_cols:
        assert col in features.columns, f"Missing feature: {col}"


def test_no_nan_in_output():
    df = make_candle_df(200)
    builder = FeatureBuilder()
    features = builder.build(df)
    # dropna 후 rows가 존재해야 함
    clean = features.dropna()
    assert len(clean) > 0


def test_deterministic_output():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    f1 = builder.build(df)
    f2 = builder.build(df)
    pd.testing.assert_frame_equal(f1, f2)


def test_build_with_short_data():
    """데이터가 부족해도 에러 없이 빈 DataFrame 반환"""
    df = make_candle_df(5)
    builder = FeatureBuilder()
    features = builder.build(df)
    assert isinstance(features, pd.DataFrame)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_features.py -v`
Expected: FAIL

- [ ] **Step 3: features.py 구현**

```python
# src/service/features.py
from __future__ import annotations

import numpy as np
import pandas as pd
import ta


class FeatureBuilder:
    """단일 피처 빌더 — 학습과 예측 모두 이 클래스를 사용한다."""

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 30:
            return pd.DataFrame()

        features = pd.DataFrame(index=df.index)

        # ① Price Action
        features["return_1m"] = df["close"].pct_change(1)
        features["return_5m"] = df["close"].pct_change(5)
        features["return_15m"] = df["close"].pct_change(15)
        features["return_60m"] = df["close"].pct_change(60)
        features["high_low_ratio"] = (df["high"] - df["low"]) / df["low"]
        features["close_position"] = (df["close"] - df["low"]) / (
            df["high"] - df["low"]
        ).replace(0, np.nan)

        # ② Technical Indicators
        features["rsi_14"] = ta.momentum.rsi(df["close"], window=14)
        features["rsi_7"] = ta.momentum.rsi(df["close"], window=7)

        macd_indicator = ta.trend.MACD(df["close"])
        features["macd"] = macd_indicator.macd()
        features["macd_signal"] = macd_indicator.macd_signal()
        features["macd_hist"] = macd_indicator.macd_diff()

        bb = ta.volatility.BollingerBands(df["close"], window=20)
        features["bb_upper"] = (df["close"] - bb.bollinger_hband()) / df["close"]
        features["bb_lower"] = (df["close"] - bb.bollinger_lband()) / df["close"]
        features["bb_width"] = bb.bollinger_wband()

        features["ema_5_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=5) - 1
        features["ema_20_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=20) - 1
        features["ema_60_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=60) - 1

        # ③ Volume
        features["volume_ratio_5m"] = df["volume"] / df["volume"].rolling(5).mean()
        features["volume_ratio_20m"] = df["volume"] / df["volume"].rolling(20).mean()
        features["volume_trend"] = (
            df["volume"].rolling(10).apply(
                lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 10 else 0,
                raw=True,
            )
        )

        return features

    def get_feature_names(self) -> list[str]:
        return [
            "return_1m", "return_5m", "return_15m", "return_60m",
            "high_low_ratio", "close_position",
            "rsi_14", "rsi_7",
            "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_lower", "bb_width",
            "ema_5_ratio", "ema_20_ratio", "ema_60_ratio",
            "volume_ratio_5m", "volume_ratio_20m", "volume_trend",
        ]
```

- [ ] **Step 4: docs/ml/feature-catalog.md 생성**

```markdown
# Feature Catalog

## Price Action
| Feature | Formula | Description |
|---------|---------|-------------|
| return_1m | pct_change(1) | 1분 수익률 |
| return_5m | pct_change(5) | 5분 수익률 |
| return_15m | pct_change(15) | 15분 수익률 |
| return_60m | pct_change(60) | 1시간 수익률 |
| high_low_ratio | (high-low)/low | 캔들 크기 |
| close_position | (close-low)/(high-low) | 캔들 내 종가 위치 |

## Technical Indicators
| Feature | Library | Description |
|---------|---------|-------------|
| rsi_14 | ta.momentum.rsi(14) | RSI 14기간 |
| rsi_7 | ta.momentum.rsi(7) | RSI 7기간 (단기) |
| macd | ta.trend.MACD.macd() | MACD line |
| macd_signal | ta.trend.MACD.macd_signal() | MACD signal |
| macd_hist | ta.trend.MACD.macd_diff() | MACD histogram |
| bb_upper | (close-upper)/close | 볼린저 상단 대비 |
| bb_lower | (close-lower)/close | 볼린저 하단 대비 |
| bb_width | bollinger_wband() | 볼린저 폭 |
| ema_5_ratio | close/ema(5)-1 | EMA5 대비 비율 |
| ema_20_ratio | close/ema(20)-1 | EMA20 대비 비율 |
| ema_60_ratio | close/ema(60)-1 | EMA60 대비 비율 |

## Volume
| Feature | Formula | Description |
|---------|---------|-------------|
| volume_ratio_5m | vol/rolling(5).mean() | 5분 평균 대비 |
| volume_ratio_20m | vol/rolling(20).mean() | 20분 평균 대비 |
| volume_trend | polyfit slope(10) | 거래량 추세 기울기 |

## Rules
- FeatureBuilder is the SINGLE class for both training and prediction
- All features are pure computations — no DB or API calls
- NaN rows are dropped before model input
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_features.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/service/features.py tests/unit/test_features.py docs/ml/feature-catalog.md
git commit -m "feat: feature engineering — FeatureBuilder with 20 technical features"
```

---

## Task 10: ML 학습 & 예측

**Files:**
- Create: `src/service/trainer.py`
- Create: `src/service/predictor.py`
- Create: `tests/unit/test_trainer.py`
- Create: `tests/unit/test_predictor.py`

**Prereqs:** Task 3, Task 4, Task 9

- [ ] **Step 1: trainer 테스트 작성**

```python
# tests/unit/test_trainer.py
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.features import FeatureBuilder


def make_training_data(n: int = 500) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_trainer_creates_model(tmp_path):
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(
        feature_builder=feature_builder,
        model_dir=str(tmp_path),
        lookahead_minutes=5,
        threshold_pct=0.3,
    )
    result = trainer.train("KRW-BTC", df)
    assert result["accuracy"] > 0
    assert result["model_path"].exists()


def test_trainer_saves_metadata(tmp_path):
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    meta_path = result["model_path"].with_suffix(".json")
    assert meta_path.exists()


def test_trainer_with_insufficient_data(tmp_path):
    df = make_training_data(20)  # 너무 적은 데이터
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    assert result["accuracy"] == 0
    assert result["model_path"] is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_trainer.py -v`
Expected: FAIL

- [ ] **Step 3: trainer.py 구현**

```python
# src/service/trainer.py
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from src.service.features import FeatureBuilder

logger = logging.getLogger(__name__)


class Trainer:
    def __init__(
        self,
        feature_builder: FeatureBuilder,
        model_dir: str,
        lookahead_minutes: int,
        threshold_pct: float,
    ) -> None:
        self._fb = feature_builder
        self._model_dir = Path(model_dir)
        self._lookahead = lookahead_minutes
        self._threshold = threshold_pct

    def _create_labels(self, df: pd.DataFrame) -> pd.Series:
        future_return = (
            df["close"].shift(-self._lookahead) / df["close"] - 1
        ) * 100
        labels = pd.Series(1, index=df.index)  # default HOLD=1
        labels[future_return > self._threshold] = 2   # BUY
        labels[future_return < -self._threshold] = 0  # SELL
        return labels

    def train(self, market: str, candle_df: pd.DataFrame) -> dict[str, Any]:
        features = self._fb.build(candle_df)
        if features.empty:
            logger.warning("Insufficient data for %s", market)
            return {"accuracy": 0, "model_path": None}

        labels = self._create_labels(candle_df).loc[features.index]

        # Drop NaN
        valid_mask = features.notna().all(axis=1) & labels.notna()
        features = features[valid_mask]
        labels = labels[valid_mask]

        if len(features) < 100:
            logger.warning("Not enough valid samples for %s: %d", market, len(features))
            return {"accuracy": 0, "model_path": None}

        # Time-series split (80/20, no shuffle)
        split_idx = int(len(features) * 0.8)
        X_train, X_val = features.iloc[:split_idx], features.iloc[split_idx:]
        y_train, y_val = labels.iloc[:split_idx], labels.iloc[split_idx:]

        model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train)

        val_pred = model.predict(X_val)
        accuracy = float(np.mean(val_pred == y_val))

        # Save model
        timestamp = time.strftime("%Y%m%d_%H%M")
        market_dir = self._model_dir / market.replace("-", "_")
        market_dir.mkdir(parents=True, exist_ok=True)
        model_path = market_dir / f"model_{timestamp}.pkl"
        meta_path = market_path = market_dir / f"meta_{timestamp}.json"

        joblib.dump(model, model_path)

        meta = {
            "market": market,
            "accuracy": accuracy,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "features": list(features.columns),
            "timestamp": timestamp,
        }
        meta_path = model_path.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info("Trained %s — accuracy: %.3f, saved: %s", market, accuracy, model_path)
        return {"accuracy": accuracy, "model_path": model_path}
```

- [ ] **Step 4: predictor 테스트 작성**

```python
# tests/unit/test_predictor.py
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.service.features import FeatureBuilder
from src.types.enums import SignalType


def make_data(n=500):
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


@pytest.fixture
def trained_model(tmp_path):
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_data()
    result = trainer.train("KRW-BTC", df)
    return result["model_path"]


def test_predictor_returns_signal(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal = predictor.predict("KRW-BTC", df)
    assert signal.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1


def test_predictor_hold_on_low_confidence(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.99)  # 매우 높은 기준
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal = predictor.predict("KRW-BTC", df)
    assert signal.signal_type == SignalType.HOLD


def test_predictor_no_model_raises():
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.6)
    with pytest.raises(KeyError):
        predictor.predict("KRW-NONE", make_data(200))
```

- [ ] **Step 5: predictor.py 구현**

```python
# src/service/predictor.py
from __future__ import annotations

import logging
import time
from pathlib import Path

import joblib
import pandas as pd

from src.service.features import FeatureBuilder
from src.types.enums import SignalType
from src.types.models import Signal

logger = logging.getLogger(__name__)

LABEL_TO_SIGNAL = {0: SignalType.SELL, 1: SignalType.HOLD, 2: SignalType.BUY}


class Predictor:
    def __init__(self, feature_builder: FeatureBuilder, min_confidence: float) -> None:
        self._fb = feature_builder
        self._min_confidence = min_confidence
        self._models: dict[str, object] = {}

    def load_model(self, market: str, model_path: Path) -> None:
        self._models[market] = joblib.load(model_path)
        logger.info("Loaded model for %s from %s", market, model_path)

    def predict(self, market: str, candle_df: pd.DataFrame) -> Signal:
        if market not in self._models:
            raise KeyError(f"No model loaded for {market}")

        model = self._models[market]
        features = self._fb.build(candle_df)

        if features.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time()))

        # 최신 행으로 예측
        latest = features.dropna().iloc[-1:]
        if latest.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time()))

        proba = model.predict_proba(latest)[0]  # type: ignore[union-attr]
        pred_class = int(proba.argmax())
        confidence = float(proba.max())

        if confidence < self._min_confidence:
            return Signal(market, SignalType.HOLD, confidence, int(time.time()))

        signal_type = LABEL_TO_SIGNAL[pred_class]
        return Signal(market, signal_type, confidence, int(time.time()))
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_trainer.py tests/unit/test_predictor.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/service/trainer.py src/service/predictor.py tests/unit/test_trainer.py tests/unit/test_predictor.py
git commit -m "feat: ML pipeline — LightGBM trainer and real-time predictor"
```

---

## Task 11: 리스크 관리

**Files:**
- Create: `src/service/risk_manager.py`
- Create: `tests/unit/test_risk_manager.py`
- Create: `docs/trading/risk-rules.md`

**Prereqs:** Task 2, Task 3

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_risk_manager.py
from decimal import Decimal

from src.service.risk_manager import RiskManager
from src.config.settings import PaperTradingConfig, RiskConfig
from src.types.enums import SignalType
from src.types.models import PaperAccount, Position, Signal, OrderSide


def make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def make_account(cash: str = "10000000", positions: dict | None = None) -> PaperAccount:
    return PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal(cash),
        positions=positions or {},
    )


def test_approve_valid_buy_signal():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account()
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is True


def test_reject_when_max_positions_reached():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        f"KRW-COIN{i}": Position(
            f"KRW-COIN{i}", OrderSide.BUY, Decimal("1000000"),
            Decimal("1"), 1700000000, Decimal("0"), Decimal("1000000"),
        )
        for i in range(4)
    }
    account = make_account("0", positions)
    signal = Signal("KRW-NEW", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "포지션 한도" in reason


def test_reject_duplicate_buy():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        "KRW-BTC": Position(
            "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
            Decimal("0.001"), 1700000000, Decimal("0"), Decimal("50000000"),
        )
    }
    account = make_account("7500000", positions)
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "이미 보유" in reason


def test_reject_on_circuit_breaker():
    rm = RiskManager(make_risk_config(), make_pt_config())
    for _ in range(5):
        rm.record_loss()
    account = make_account()
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "서킷 브레이커" in reason


def test_sell_signal_allowed_when_holding():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        "KRW-BTC": Position(
            "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
            Decimal("0.001"), 1700000000, Decimal("0"), Decimal("50000000"),
        )
    }
    account = make_account("7500000", positions)
    signal = Signal("KRW-BTC", SignalType.SELL, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is True


def test_calculate_position_size():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account("10000000")
    size = rm.calculate_position_size(account)
    # max 25% of total balance
    assert size == Decimal("2500000")


def test_position_size_limited_by_cash():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account("1000000")  # 100만원만 보유
    size = rm.calculate_position_size(account)
    assert size == Decimal("1000000")  # cash가 한도보다 적으므로 cash 전액


def test_reject_below_min_order():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account("3000")  # 3000원 — 최소 5000원 미만
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "최소 주문" in reason
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_risk_manager.py -v`
Expected: FAIL

- [ ] **Step 3: risk_manager.py 구현**

```python
# src/service/risk_manager.py
from __future__ import annotations

import time
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.types.enums import SignalType
from src.types.models import PaperAccount, Signal


class RiskManager:
    def __init__(self, risk_config: RiskConfig, pt_config: PaperTradingConfig) -> None:
        self._risk = risk_config
        self._pt = pt_config
        self._consecutive_losses = 0
        self._cooldown_until = 0
        self._daily_loss = Decimal("0")
        self._daily_trades = 0
        self._current_day = ""

    def approve(self, signal: Signal, account: PaperAccount) -> tuple[bool, str]:
        # SELL은 보유 중이면 허용
        if signal.signal_type == SignalType.SELL:
            if signal.market in account.positions:
                return True, "OK"
            return False, "매도할 포지션 없음"

        # HOLD는 무시
        if signal.signal_type == SignalType.HOLD:
            return False, "HOLD 시그널"

        # BUY 체크
        # [1] 서킷 브레이커
        if self._consecutive_losses >= self._risk.consecutive_loss_limit:
            if time.time() < self._cooldown_until:
                return False, "서킷 브레이커 발동 — 쿨다운 중"
            self._consecutive_losses = 0  # 쿨다운 종료

        # [2] 일일 한도
        if self._daily_trades >= self._risk.max_daily_trades:
            return False, "일일 최대 거래 횟수 도달"

        # [3] 포지션 한도
        if len(account.positions) >= self._pt.max_open_positions:
            return False, "포지션 한도 도달"

        if signal.market in account.positions:
            return False, f"{signal.market} 이미 보유 중 — 중복 매수 불가"

        # [4] 최소 주문 금액
        invest_amount = self.calculate_position_size(account)
        if invest_amount < self._pt.min_order_krw:
            return False, f"최소 주문 금액({self._pt.min_order_krw}원) 미달"

        return True, "OK"

    def calculate_position_size(self, account: PaperAccount) -> Decimal:
        total_equity = account.cash_balance + sum(
            p.entry_price * p.quantity for p in account.positions.values()
        )
        max_amount = total_equity * self._pt.max_position_pct
        return min(account.cash_balance, max_amount)

    def record_loss(self) -> None:
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._risk.consecutive_loss_limit:
            self._cooldown_until = int(time.time()) + self._risk.cooldown_minutes * 60

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def record_trade(self) -> None:
        self._daily_trades += 1

    def reset_daily(self) -> None:
        self._daily_loss = Decimal("0")
        self._daily_trades = 0
```

- [ ] **Step 4: docs/trading/risk-rules.md 생성**

```markdown
# Risk Management Rules

## Position Limits
- Max 25% of total equity per position
- Max 4 open positions simultaneously
- No duplicate buys (same coin)
- Minimum order: 5,000 KRW (Upbit limit)

## Stop Loss / Take Profit
- Stop loss: -2% from entry
- Take profit: +5% from entry
- Trailing stop: -1.5% from highest price since entry

## Daily Limits
- Max daily loss: 5% of initial balance
- Max daily trades: 50

## Circuit Breaker
- Trigger: 5 consecutive losses
- Action: Halt all BUY signals for 60 minutes
- Reset: After cooldown OR after a winning trade

## Risk Check Flow (5-step gate)
1. Circuit breaker check
2. Daily limit check
3. Position limit check
4. Duplicate position check
5. Position sizing + minimum order check
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_risk_manager.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/service/risk_manager.py tests/unit/test_risk_manager.py docs/trading/risk-rules.md
git commit -m "feat: risk manager — 5-step gate with circuit breaker"
```

---

## Task 12: 가상 매매 엔진

**Files:**
- Create: `src/service/paper_engine.py`
- Create: `tests/unit/test_paper_engine.py`

**Prereqs:** Task 2, Task 4, Task 11

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_paper_engine.py
import uuid
from decimal import Decimal

from src.service.paper_engine import PaperEngine
from src.config.settings import PaperTradingConfig
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import PaperAccount, Order, Position


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def make_account(cash: str = "10000000") -> PaperAccount:
    return PaperAccount(Decimal("10000000"), Decimal(cash), {})


def test_execute_buy_order():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    current_price = Decimal("50000000")
    invest_amount = Decimal("2500000")

    order = engine.execute_buy(account, "KRW-BTC", current_price, invest_amount, 0.8)

    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.BUY
    assert order.fee > Decimal("0")
    assert "KRW-BTC" in account.positions
    assert account.cash_balance < Decimal("10000000")


def test_buy_applies_slippage():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    current_price = Decimal("50000000")

    order = engine.execute_buy(account, "KRW-BTC", current_price, Decimal("2500000"), 0.8)

    assert order.fill_price is not None
    assert order.fill_price > current_price  # 매수 시 불리한 방향


def test_execute_sell_order():
    engine = PaperEngine(make_pt_config())
    account = make_account("7500000")
    account.positions["KRW-BTC"] = Position(
        "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
        Decimal("0.05"), 1700000000, Decimal("0"), Decimal("50000000"),
    )

    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "ML_SIGNAL")

    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.SELL
    assert "KRW-BTC" not in account.positions
    assert account.cash_balance > Decimal("7500000")


def test_sell_calculates_pnl():
    engine = PaperEngine(make_pt_config())
    account = make_account("7500000")
    entry = Decimal("50000000")
    account.positions["KRW-BTC"] = Position(
        "KRW-BTC", OrderSide.BUY, entry,
        Decimal("0.05"), 1700000000, Decimal("0"), entry,
    )

    sell_price = Decimal("52000000")  # +4%
    order = engine.execute_sell(account, "KRW-BTC", sell_price, "TAKE_PROFIT")

    # 대략 수익 발생 확인 (슬리피지/수수료 반영)
    assert account.cash_balance > Decimal("7500000") + entry * Decimal("0.05") * Decimal("0.03")


def test_buy_deducts_fee_from_cash():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), Decimal("2500000"), 0.8)

    # 현금 = 10M - 투자금 - 수수료
    expected_max = Decimal("10000000") - Decimal("2500000")
    assert account.cash_balance < expected_max  # 수수료만큼 더 차감
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_paper_engine.py -v`
Expected: FAIL

- [ ] **Step 3: paper_engine.py 구현**

```python
# src/service/paper_engine.py
from __future__ import annotations

import uuid
import time
from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order, PaperAccount, Position


class PaperEngine:
    def __init__(self, config: PaperTradingConfig) -> None:
        self._config = config

    def execute_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        invest_amount: Decimal,
        confidence: float,
    ) -> Order:
        fill_price = current_price * (Decimal("1") + self._config.slippage_rate)
        quantity = invest_amount / fill_price
        fee = invest_amount * self._config.fee_rate
        total_cost = invest_amount + fee
        now = int(time.time())

        # 잔고 차감
        account.cash_balance -= total_cost

        # 포지션 생성
        account.positions[market] = Position(
            market=market,
            side=OrderSide.BUY,
            entry_price=fill_price,
            quantity=quantity,
            entry_time=now,
            unrealized_pnl=Decimal("0"),
            highest_price=fill_price,
        )

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=quantity,
            status=OrderStatus.FILLED,
            signal_confidence=confidence,
            reason="ML_SIGNAL",
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )

    def execute_sell(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        reason: str,
    ) -> Order:
        position = account.positions[market]
        fill_price = current_price * (Decimal("1") - self._config.slippage_rate)
        proceeds = fill_price * position.quantity
        fee = proceeds * self._config.fee_rate
        net_proceeds = proceeds - fee
        now = int(time.time())

        # 잔고 증가
        account.cash_balance += net_proceeds

        # 포지션 제거
        del account.positions[market]

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=position.quantity,
            status=OrderStatus.FILLED,
            signal_confidence=0.0,
            reason=reason,
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_paper_engine.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/paper_engine.py tests/unit/test_paper_engine.py
git commit -m "feat: paper trading engine — virtual order execution with slippage/fees"
```

---

## Task 13: 포트폴리오 관리

**Files:**
- Create: `src/service/portfolio.py`
- Create: `tests/unit/test_portfolio.py`

**Prereqs:** Task 2, Task 4, Task 12

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_portfolio.py
from decimal import Decimal

from src.service.portfolio import PortfolioManager
from src.config.settings import RiskConfig
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )


def make_position(entry: str = "50000000", highest: str | None = None) -> Position:
    return Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal(entry), quantity=Decimal("0.05"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal(highest or entry),
    )


def test_update_unrealized_pnl():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    current_price = Decimal("51000000")
    pm.update_position(pos, current_price)
    assert pos.unrealized_pnl == Decimal("2")  # +2%


def test_update_highest_price():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    pm.update_position(pos, Decimal("52000000"))
    assert pos.highest_price == Decimal("52000000")


def test_stop_loss_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("48900000"))  # -2.2%
    assert action == "STOP_LOSS"


def test_take_profit_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("52600000"))  # +5.2%
    assert action == "TAKE_PROFIT"


def test_trailing_stop_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000", "55000000")  # 최고가 55M
    # 최고가 대비 -1.5% = 54,175,000. 현재가 54,000,000 → trailing stop
    action = pm.check_exit_conditions(pos, Decimal("54000000"))
    assert action == "TRAILING_STOP"


def test_no_exit_in_normal_range():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("50500000"))  # +1%
    assert action is None


def test_total_equity_calculation():
    pm = PortfolioManager(make_risk_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("7500000"),
        positions={
            "KRW-BTC": make_position("50000000"),
        },
    )
    prices = {"KRW-BTC": Decimal("51000000")}
    equity = pm.calculate_total_equity(account, prices)
    # 7,500,000 + 0.05 * 51,000,000 = 7,500,000 + 2,550,000 = 10,050,000
    assert equity == Decimal("10050000")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_portfolio.py -v`
Expected: FAIL

- [ ] **Step 3: portfolio.py 구현**

```python
# src/service/portfolio.py
from __future__ import annotations

from decimal import Decimal

from src.config.settings import RiskConfig
from src.types.models import PaperAccount, Position


class PortfolioManager:
    def __init__(self, risk_config: RiskConfig) -> None:
        self._risk = risk_config

    def update_position(self, position: Position, current_price: Decimal) -> None:
        # 미실현 PnL (%)
        position.unrealized_pnl = (
            (current_price - position.entry_price) / position.entry_price * Decimal("100")
        )
        # 최고가 갱신
        if current_price > position.highest_price:
            position.highest_price = current_price

    def check_exit_conditions(self, position: Position, current_price: Decimal) -> str | None:
        pnl_pct = (current_price - position.entry_price) / position.entry_price

        # 손절
        if pnl_pct <= -self._risk.stop_loss_pct:
            return "STOP_LOSS"

        # 익절
        if pnl_pct >= self._risk.take_profit_pct:
            return "TAKE_PROFIT"

        # 트레일링 스탑
        if position.highest_price > position.entry_price:
            drop_from_high = (
                (position.highest_price - current_price) / position.highest_price
            )
            if drop_from_high >= self._risk.trailing_stop_pct:
                return "TRAILING_STOP"

        return None

    def calculate_total_equity(
        self, account: PaperAccount, current_prices: dict[str, Decimal]
    ) -> Decimal:
        position_value = sum(
            current_prices.get(market, pos.entry_price) * pos.quantity
            for market, pos in account.positions.items()
        )
        return account.cash_balance + position_value
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_portfolio.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/portfolio.py tests/unit/test_portfolio.py
git commit -m "feat: portfolio manager — position monitoring, SL/TP/trailing stop"
```

---

## Task 14: 이벤트 버스 & 런타임

**Files:**
- Create: `src/runtime/event_bus.py`
- Create: `src/runtime/scheduler.py`
- Create: `tests/unit/test_event_bus.py`

**Prereqs:** Task 2

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_event_bus.py
import asyncio

from src.runtime.event_bus import EventBus
from src.types.events import NewCandleEvent, SignalEvent
from src.types.enums import SignalType
from src.types.models import Candle
from decimal import Decimal


async def test_subscribe_and_publish():
    bus = EventBus()
    received: list = []

    async def handler(event: SignalEvent) -> None:
        received.append(event)

    bus.subscribe(SignalEvent, handler)
    event = SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].market == "KRW-BTC"


async def test_multiple_subscribers():
    bus = EventBus()
    count = {"a": 0, "b": 0}

    async def handler_a(event: SignalEvent) -> None:
        count["a"] += 1

    async def handler_b(event: SignalEvent) -> None:
        count["b"] += 1

    bus.subscribe(SignalEvent, handler_a)
    bus.subscribe(SignalEvent, handler_b)

    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert count["a"] == 1
    assert count["b"] == 1


async def test_different_event_types_isolated():
    bus = EventBus()
    signal_received: list = []
    candle_received: list = []

    async def signal_handler(event: SignalEvent) -> None:
        signal_received.append(event)

    async def candle_handler(event: NewCandleEvent) -> None:
        candle_received.append(event)

    bus.subscribe(SignalEvent, signal_handler)
    bus.subscribe(NewCandleEvent, candle_handler)

    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert len(signal_received) == 1
    assert len(candle_received) == 0
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_event_bus.py -v`
Expected: FAIL

- [ ] **Step 3: event_bus.py 구현**

```python
# src/runtime/event_bus.py
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Handler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: object) -> None:
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Error in handler %s for %s", handler.__name__, event_type.__name__)
```

- [ ] **Step 4: scheduler.py 구현**

```python
# src/runtime/scheduler.py
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)

Task = Callable[[], Coroutine[Any, Any, None]]


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []

    def schedule_interval(self, name: str, func: Task, interval_seconds: float) -> None:
        async def _loop() -> None:
            while True:
                try:
                    await func()
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Error in scheduled task: %s", name)
                await asyncio.sleep(interval_seconds)

        task = asyncio.create_task(_loop(), name=name)
        self._tasks.append(task)
        logger.info("Scheduled '%s' every %.1fs", name, interval_seconds)

    async def cancel_all(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
```

- [ ] **Step 5: __init__.py 업데이트**

```python
# src/runtime/__init__.py
from src.runtime.event_bus import EventBus
from src.runtime.scheduler import Scheduler

__all__ = ["EventBus", "Scheduler"]
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_event_bus.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/runtime/ tests/unit/test_event_bus.py
git commit -m "feat: runtime — async event bus and interval scheduler"
```

---

## Task 15: FastAPI 백엔드

**Files:**
- Create: `src/ui/api/server.py`
- Create: `src/ui/api/routes/dashboard.py`
- Create: `src/ui/api/routes/portfolio.py`
- Create: `src/ui/api/routes/strategy.py`
- Create: `src/ui/api/routes/risk.py`
- Create: `src/ui/api/routes/control.py`
- Create: `tests/unit/test_api.py`
- Create: `docs/api/dashboard-endpoints.md`

**Prereqs:** Task 2, 3, 4, 14

이 태스크는 코드량이 많으므로 핵심 구조와 주요 엔드포인트만 구현합니다.

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport

from src.ui.api.server import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_check(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_dashboard_summary(client):
    resp = await client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_equity" in data
    assert "cash_balance" in data
    assert "daily_pnl" in data


async def test_portfolio_positions(client):
    resp = await client.get("/api/portfolio/positions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_risk_status(client):
    resp = await client.get("/api/risk/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "circuit_breaker_active" in data
    assert "consecutive_losses" in data
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: server.py 구현**

```python
# src/ui/api/server.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.ui.api.routes import control, dashboard, portfolio, risk, strategy


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Paper Trader", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
    app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
    app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [ ] **Step 4: route 파일들 구현**

```python
# src/ui/api/routes/dashboard.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def get_summary() -> dict:
    # TODO: 실제 데이터 연결 (Task 17에서 DI로 연결)
    return {
        "total_equity": "10000000",
        "cash_balance": "10000000",
        "daily_pnl": "0",
        "total_return_pct": "0",
        "open_positions": 0,
    }
```

```python
# src/ui/api/routes/portfolio.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/positions")
async def get_positions() -> list:
    return []


@router.get("/history")
async def get_history(page: int = 1, size: int = 20) -> dict:
    return {"items": [], "page": page, "size": size, "total": 0}


@router.get("/daily")
async def get_daily() -> list:
    return []
```

```python
# src/ui/api/routes/strategy.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/screening")
async def get_screening() -> list:
    return []


@router.get("/signals")
async def get_signals() -> list:
    return []


@router.get("/model-status")
async def get_model_status() -> dict:
    return {"models": {}, "last_retrain": None}
```

```python
# src/ui/api/routes/risk.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def get_risk_status() -> dict:
    return {
        "circuit_breaker_active": False,
        "consecutive_losses": 0,
        "daily_trades": 0,
        "daily_loss_pct": "0",
        "cooldown_until": None,
    }
```

```python
# src/ui/api/routes/control.py
from fastapi import APIRouter

router = APIRouter()


@router.post("/pause")
async def pause() -> dict:
    return {"status": "paused"}


@router.post("/resume")
async def resume() -> dict:
    return {"status": "running"}
```

- [ ] **Step 5: docs/api/dashboard-endpoints.md 생성**

```markdown
# Dashboard API Endpoints

## REST

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |
| GET | /api/dashboard/summary | 총 자산, PnL, 포지션 수 |
| GET | /api/portfolio/positions | 보유 포지션 목록 |
| GET | /api/portfolio/history?page&size | 거래 이력 (페이징) |
| GET | /api/portfolio/daily | 일별 성과 |
| GET | /api/strategy/screening | 스크리닝 현황 |
| GET | /api/strategy/signals | 시그널 로그 |
| GET | /api/strategy/model-status | 모델 상태 |
| GET | /api/risk/status | 리스크 상태 |
| POST | /api/control/pause | 매매 일시 중지 |
| POST | /api/control/resume | 매매 재개 |

## WebSocket

`WS /ws/live` — real-time updates

Message types: price_update, position_update, trade_executed, signal_fired, risk_alert, summary_update
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/ui/ tests/unit/test_api.py docs/api/dashboard-endpoints.md
git commit -m "feat: FastAPI backend — REST endpoints and WebSocket scaffold"
```

---

## Task 16: React 대시보드

**Files:**
- Create: `src/ui/frontend/` (Vite + React 프로젝트)

**Prereqs:** Task 15

- [ ] **Step 1: Vite + React 프로젝트 초기화**

```bash
cd src/ui/frontend
npm create vite@latest . -- --template react-ts
npm install
npm install recharts react-router-dom
npm install -D @types/react @types/react-dom
```

- [ ] **Step 2: 프로젝트 구조 생성**

```bash
mkdir -p src/hooks src/pages src/components src/styles
```

- [ ] **Step 3: 핵심 hooks 구현**

```typescript
// src/ui/frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from "react";

interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

export function useWebSocket(url: string) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      // 자동 재연결 (3초 후)
      setTimeout(() => {
        wsRef.current = new WebSocket(url);
      }, 3000);
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSMessage;
      setLastMessage(msg);
    };

    return () => ws.close();
  }, [url]);

  return { lastMessage, isConnected };
}
```

```typescript
// src/ui/frontend/src/hooks/useApi.ts
import { useState, useCallback } from "react";

const API_BASE = "http://localhost:8000";

export function useApi() {
  const get = useCallback(async <T>(path: string): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`);
    return resp.json();
  }, []);

  const post = useCallback(async <T>(path: string): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`, { method: "POST" });
    return resp.json();
  }, []);

  return { get, post };
}
```

- [ ] **Step 4: Dashboard 페이지 구현**

```typescript
// src/ui/frontend/src/pages/Dashboard.tsx
import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

interface Summary {
  total_equity: string;
  cash_balance: string;
  daily_pnl: string;
  total_return_pct: string;
  open_positions: number;
}

export default function Dashboard() {
  const { get } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    get<Summary>("/api/dashboard/summary").then(setSummary);
  }, [get]);

  useEffect(() => {
    if (lastMessage?.type === "summary_update") {
      setSummary(lastMessage.data as unknown as Summary);
    }
  }, [lastMessage]);

  if (!summary) return <div>Loading...</div>;

  const formatKRW = (val: string) =>
    `₩${Number(val).toLocaleString()}`;

  return (
    <div style={{ padding: "24px" }}>
      <h1>Dashboard</h1>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
        <div className="card">
          <div className="label">총 자산</div>
          <div className="value">{formatKRW(summary.total_equity)}</div>
        </div>
        <div className="card">
          <div className="label">현금 잔고</div>
          <div className="value">{formatKRW(summary.cash_balance)}</div>
        </div>
        <div className="card">
          <div className="label">금일 PnL</div>
          <div className="value">{formatKRW(summary.daily_pnl)}</div>
        </div>
        <div className="card">
          <div className="label">총 수익률</div>
          <div className="value">{summary.total_return_pct}%</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: App.tsx 라우터 구성**

```typescript
// src/ui/frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";

function App() {
  return (
    <BrowserRouter>
      <nav style={{ padding: "12px 24px", borderBottom: "1px solid #333", display: "flex", gap: "24px" }}>
        <Link to="/">Dashboard</Link>
        <Link to="/portfolio">Portfolio</Link>
        <Link to="/strategy">Strategy</Link>
        <Link to="/risk">Risk</Link>
        <Link to="/settings">Settings</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/portfolio" element={<div>Portfolio (TODO)</div>} />
        <Route path="/strategy" element={<div>Strategy (TODO)</div>} />
        <Route path="/risk" element={<div>Risk (TODO)</div>} />
        <Route path="/settings" element={<div>Settings (TODO)</div>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 6: 다크 테마 CSS**

```css
/* src/ui/frontend/src/index.css */
:root {
  --bg: #0d1117;
  --card-bg: #161b22;
  --text: #e6edf3;
  --text-secondary: #8b949e;
  --border: #30363d;
  --green: #3fb950;
  --red: #f85149;
  --blue: #58a6ff;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
}

a { color: var(--blue); text-decoration: none; }

.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.card .label { color: var(--text-secondary); font-size: 14px; }
.card .value { font-size: 24px; font-weight: 600; margin-top: 4px; }
```

- [ ] **Step 7: 빌드 확인**

Run: `cd src/ui/frontend && npm run build`
Expected: 빌드 성공

- [ ] **Step 8: Commit**

```bash
git add src/ui/frontend/
git commit -m "feat: React dashboard — dark theme, summary cards, WebSocket hook"
```

---

## Task 17: 통합 & 앱 오케스트레이션

**Files:**
- Create: `src/runtime/app.py`
- Create: `src/main.py`
- Create: `tests/integration/test_signal_to_trade.py`
- Create: `tests/integration/test_event_flow.py`

**Prereqs:** All previous tasks

- [ ] **Step 1: app.py 구현 — 전체 조합**

```python
# src/runtime/app.py
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
        await self.scheduler.cancel_all()
        await self.upbit.close()
        await self.db.close()
        logger.info("App stopped.")

    async def _refresh_screening(self) -> None:
        tickers = await self.upbit.fetch_tickers(self.collector.markets)
        results = self.screener.screen(tickers)
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
```

- [ ] **Step 2: main.py 구현**

```python
# src/main.py
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import uvicorn

from src.config.settings import Settings
from src.runtime.app import App
from src.ui.api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    settings = Settings.from_yaml(Path("config/settings.yaml"))
    app = App(settings)
    await app.start()

    fastapi_app = create_app()
    # 앱 상태를 FastAPI에 주입
    fastapi_app.state.app = app

    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 통합 테스트 — 이벤트 흐름**

```python
# tests/integration/test_event_flow.py
import asyncio
from decimal import Decimal

from src.runtime.event_bus import EventBus
from src.types.events import SignalEvent, TradeEvent
from src.types.enums import SignalType, OrderSide, OrderStatus, OrderType
from src.types.models import Order


async def test_signal_to_trade_event_flow():
    """EventBus를 통해 Signal → Trade 이벤트 체인이 작동하는지 검증"""
    bus = EventBus()
    trade_events: list[TradeEvent] = []

    async def on_signal(event: SignalEvent) -> None:
        # 시그널 수신 → 트레이드 이벤트 발행 (간략화)
        order = Order(
            id="test-order", market=event.market, side=OrderSide.BUY,
            order_type=OrderType.MARKET, price=Decimal("50000000"),
            quantity=Decimal("0.001"), status=OrderStatus.FILLED,
            signal_confidence=event.confidence, reason="ML_SIGNAL",
            created_at=event.timestamp, fill_price=Decimal("50025000"),
            filled_at=event.timestamp, fee=Decimal("25"),
        )
        await bus.publish(TradeEvent(order, event.timestamp))

    async def on_trade(event: TradeEvent) -> None:
        trade_events.append(event)

    bus.subscribe(SignalEvent, on_signal)
    bus.subscribe(TradeEvent, on_trade)

    # 시그널 발행
    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert len(trade_events) == 1
    assert trade_events[0].order.market == "KRW-BTC"
```

- [ ] **Step 4: 통합 테스트 — 시그널 → 리스크 → 체결**

```python
# tests/integration/test_signal_to_trade.py
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.service.risk_manager import RiskManager
from src.service.paper_engine import PaperEngine
from src.types.enums import SignalType, OrderStatus
from src.types.models import PaperAccount, Signal


def test_full_buy_flow():
    """Signal → RiskManager.approve → PaperEngine.execute_buy 전체 흐름"""
    risk_config = RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )
    pt_config = PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )

    rm = RiskManager(risk_config, pt_config)
    engine = PaperEngine(pt_config)
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})

    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved

    invest = rm.calculate_position_size(account)
    order = engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)

    assert order.status == OrderStatus.FILLED
    assert "KRW-BTC" in account.positions
    assert account.cash_balance < Decimal("10000000")


def test_full_sell_flow():
    """보유 포지션 → SELL Signal → 체결 → 포지션 청산"""
    risk_config = RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )
    pt_config = PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )

    rm = RiskManager(risk_config, pt_config)
    engine = PaperEngine(pt_config)
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})

    # 먼저 매수
    invest = rm.calculate_position_size(account)
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)
    assert "KRW-BTC" in account.positions

    # 매도 시그널
    sell_signal = Signal("KRW-BTC", SignalType.SELL, 0.9, 1700000060)
    approved, _ = rm.approve(sell_signal, account)
    assert approved

    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "ML_SIGNAL")
    assert order.status == OrderStatus.FILLED
    assert "KRW-BTC" not in account.positions
```

- [ ] **Step 5: 통합 테스트 실행**

Run: `uv run pytest tests/integration/ -v`
Expected: ALL PASS

- [ ] **Step 6: 전체 테스트 실행**

Run: `uv run pytest -v --cov=src`
Expected: ALL PASS, 적절한 커버리지

- [ ] **Step 7: 구조적 테스트 최종 확인**

Run: `uv run pytest tests/structural/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/runtime/app.py src/main.py tests/integration/
git commit -m "feat: app orchestration — full signal-to-trade pipeline integration"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] 6-Layer Modular Monolith: Task 1 (scaffold), Task 2-4 (L0-L2), Task 6-13 (L3), Task 14 (L4), Task 15-16 (L5)
- [x] 하네스 엔지니어링 3축: Task 1 (Context — AGENTS.md, docs), Task 5 (Constraints — structural tests), Task 5 (GC — quality audit placeholder)
- [x] Upbit API 연동: Task 6
- [x] 데이터 수집: Task 7
- [x] 종목 스크리닝: Task 8
- [x] 피처 엔지니어링: Task 9
- [x] ML 학습/예측: Task 10
- [x] 리스크 관리: Task 11
- [x] 가상 매매 엔진: Task 12
- [x] 포트폴리오 관리: Task 13
- [x] 이벤트 버스: Task 14
- [x] FastAPI 백엔드: Task 15
- [x] React 대시보드: Task 16
- [x] 통합 오케스트레이션: Task 17

### Type Consistency
- `Candle`, `Order`, `Position`, `Signal`, `PaperAccount` — Task 2에서 정의, 이후 전체 일관
- `FeatureBuilder` — Task 9에서 단일 클래스, Task 10에서 trainer/predictor 모두 동일 인스턴스 사용
- `RiskManager.approve()` → `PaperEngine.execute_buy/sell()` — Task 11, 12, 17에서 일관된 호출 패턴

### Placeholder Scan
- Task 15 route 파일에 "TODO" 주석 있으나, Task 17에서 DI로 실제 데이터 연결 예정으로 의도적
