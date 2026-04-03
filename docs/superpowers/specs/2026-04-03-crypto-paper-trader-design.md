# Crypto Paper Trader - Design Spec

## Overview

Upbit 원화 마켓 실시간 시세 기반의 가상 매매(페이퍼 트레이딩) 시스템.
ML 모델(XGBoost/LightGBM)로 매매 시그널을 생성하고, 가상 자금으로 매매를 시뮬레이션하여 전략 성능을 검증한다.

**OpenAI 하네스 엔지니어링** 원칙에 의거하여 설계 및 구현한다.

### 핵심 요구사항

| 항목 | 결정 |
|------|------|
| 거래소 | Upbit (KRW 마켓, Public API - 인증 불필요) |
| 전략 | ML 기반 — XGBoost / LightGBM (3-class 분류: BUY/SELL/HOLD) |
| 언어 | Python |
| 결과 확인 | 웹 대시보드 (FastAPI + React) |
| 매매 대상 | 거래량/변동성 기준 자동 스크리닝 (최대 10종목) |
| 시드머니 | 1,000만원 (가상), 종목당 최대 25% |
| 주기 | 분봉 단위 (1분~5분) |
| 아키텍처 | 모듈러 모놀리스 (6-Layer) |

---

## 1. 하네스 엔지니어링 원칙

> **Coding Agent = AI Model + Harness**
> 모델은 말(horse), 하네스는 고삐/안장/재갈. 엔지니어는 기수(rider).

### 1.1 Three Pillars

| 축 | 핵심 | 프로젝트 적용 |
|---|---|---|
| **Context Engineering** | 에이전트에게 지도를 주되 백과사전은 주지 않는다 | `AGENTS.md` 60줄 이하, 설계 문서/아키텍처 맵 모두 레포 안에 버전관리 |
| **Architectural Constraints** | 의존성 단방향 레이어링, 구조적 테스트로 기계적 경계 강제 | `Types -> Config -> Repo -> Service -> Runtime -> UI` 레이어 규칙, pre-commit 훅 |
| **Garbage Collection** | 주기적 자동 정리로 코드 엔트로피 방지 | 품질 감사 스크립트, 오래된 데이터/모델 자동 정리, 문서-코드 정합성 검증 |

### 1.2 제어 체계 (Feedforward + Feedback)

```
               Feedforward              Feedback
            (사전 가이드)              (사후 교정)
           ┌─────────────┐         ┌──────────────┐
Computa-   │ ruff lint    │         │ 구조적 테스트   │
tional     │ mypy strict  │         │ 단위 테스트    │
(결정론적)  │ layer check  │         │ CI 파이프라인   │
           └─────────────┘         └──────────────┘
           ┌─────────────┐         ┌──────────────┐
Inferen-   │ AGENTS.md    │         │ quality_audit │
tial       │ 아키텍처 문서  │         │ 모델 성능 감시  │
(의미 판단)  │ ADR          │         │ 코드 리뷰      │
           └─────────────┘         └──────────────┘

Timing:
  Pre-commit  → ruff, mypy, structural tests (초 단위)
  CI          → 전체 테스트 스위트 (분 단위)
  Weekly      → quality_audit.py (엔트로피 방지)
```

---

## 2. 프로젝트 구조 (6-Layer Modular Monolith)

```
crypto-paper-trader/
│
├── AGENTS.md                    # 에이전트용 목차 (60줄 이하)
├── CLAUDE.md                    # Claude Code 전용 지침
├── pyproject.toml               # 의존성 (uv)
├── ruff.toml                    # 린터/포매터 설정
├── mypy.ini                     # 타입 체크 설정
│
├── config/
│   └── settings.yaml            # 런타임 설정 (시드머니, 비율, 주기)
│
├── docs/                        # 설계 문서 (레포 = 진실의 원천)
│   ├── architecture.md          # 아키텍처 맵
│   ├── layer-rules.md           # 의존성 레이어 규칙
│   ├── api/
│   │   ├── upbit-limits.md      # Upbit API 제한사항
│   │   ├── dashboard-endpoints.md # 대시보드 API 명세
│   │   └── ws-schema.json       # WebSocket 메시지 스키마
│   ├── ml/
│   │   └── feature-catalog.md   # 피처 목록/의미/계산식
│   ├── trading/
│   │   └── risk-rules.md        # 리스크 규칙과 근거
│   ├── decisions/               # ADR (Architecture Decision Records)
│   └── superpowers/specs/       # 설계 스펙
│
├── src/
│   ├── types/                   # Layer 0: 순수 타입/모델
│   │   ├── models.py            #   Candle, Order, Position, Signal, PaperAccount
│   │   └── enums.py             #   OrderSide, SignalType, OrderStatus, CoinStatus
│   │
│   ├── config/                  # Layer 1: 설정 (types만 의존)
│   │   └── settings.py          #   Pydantic Settings 로더
│   │
│   ├── repository/              # Layer 2: 데이터 접근 (types, config만 의존)
│   │   ├── database.py          #   SQLite 연결 (→ PostgreSQL 전환 가능)
│   │   ├── candle_repo.py       #   캔들 CRUD
│   │   ├── order_repo.py        #   주문 CRUD
│   │   └── portfolio_repo.py    #   포트폴리오 CRUD
│   │
│   ├── service/                 # Layer 3: 비즈니스 로직 (하위 레이어만 의존)
│   │   ├── collector.py         #   Upbit 데이터 수집
│   │   ├── upbit_client.py      #   Upbit REST/WebSocket API 래퍼
│   │   ├── screener.py          #   종목 스크리닝 (거래량/변동성)
│   │   ├── features.py          #   피처 엔지니어링
│   │   ├── trainer.py           #   XGBoost/LightGBM 학습
│   │   ├── predictor.py         #   실시간 예측
│   │   ├── paper_engine.py      #   가상 주문 체결 엔진
│   │   ├── risk_manager.py      #   리스크 관리
│   │   └── portfolio.py         #   포트폴리오 추적
│   │
│   ├── runtime/                 # Layer 4: 오케스트레이션 (서비스 조합)
│   │   ├── event_bus.py         #   내부 이벤트 버스
│   │   ├── scheduler.py         #   수집/예측 스케줄러
│   │   └── app.py               #   앱 라이프사이클 관리
│   │
│   └── ui/                      # Layer 5: 프레젠테이션 (최상위)
│       ├── api/                 #   FastAPI 엔드포인트
│       │   ├── server.py
│       │   └── routes/
│       └── frontend/            #   React 대시보드
│
├── scripts/                     # 하네스 도구
│   ├── check_layers.py          #   의존성 방향 검증 스크립트
│   ├── quality_audit.py         #   품질 감사 (GC 축)
│   └── bootstrap.py             #   프로젝트 초기 설정
│
├── tests/                       # 모듈별 테스트
│   ├── unit/                    #   단위 테스트
│   ├── integration/             #   통합 테스트
│   └── structural/              #   아키텍처 규칙 검증 테스트
│       └── test_layer_deps.py   #   레이어 의존성 위반 감지
│
├── data/                        # 로컬 데이터
│   └── models/                  #   학습된 모델 파일
│
└── .pre-commit-config.yaml      # pre-commit 훅 설정
```

### 2.1 의존성 레이어 규칙 (단방향 강제)

```
Layer 0: types/      ← 아무것도 의존하지 않음
Layer 1: config/     ← types만 의존
Layer 2: repository/ ← types, config만 의존
Layer 3: service/    ← types, config, repository만 의존
Layer 4: runtime/    ← types, config, repository, service만 의존
Layer 5: ui/         ← 모든 하위 레이어 의존 가능
```

`scripts/check_layers.py`와 `tests/structural/test_layer_deps.py`로 기계적으로 강제한다.
위반 시 pre-commit과 CI에서 실패한다.

### 2.2 이벤트 흐름

```
collector  →[NewCandleEvent]→       screener
screener   →[ScreenedCoinsEvent]→   predictor
predictor  →[SignalEvent]→          risk_manager → paper_engine
paper_engine →[TradeEvent]→         portfolio → dashboard (WebSocket push)
```

모듈 간 직접 import 대신 `runtime/event_bus.py`의 이벤트 버스를 통해 느슨하게 연결.
나중에 서비스 분리 시 이벤트 버스만 Kafka/Redis로 교체 가능.

---

## 3. 데이터 수집 & 종목 스크리닝

### 3.1 Upbit API 연동

API 키 없이 Public API로 시세 조회 (가상 매매이므로 인증 불필요).

```
[Upbit Public API]
├── GET /v1/market/all              # 전체 마켓 목록
├── GET /v1/candles/minutes/{unit}  # 분봉 (1, 3, 5, 10, 15, 30, 60, 240)
├── GET /v1/ticker                  # 현재가 정보 (복수 종목)
└── WebSocket wss://api.upbit.com/websocket/v1
    ├── ticker    # 현재가 실시간
    ├── trade     # 체결 실시간
    └── orderbook # 호가 실시간
```

**Rate Limit 관리**:

| API | 제한 | 대응 |
|-----|------|------|
| REST 조회 | 초당 10회 | 요청 큐 + 쓰로틀링 |
| WebSocket | 연결당 15개 구독 | 종목 수에 따라 다중 연결 |

### 3.2 데이터 수집 파이프라인

```
[1단계: 마켓 목록 수집]
  - 앱 시작 시 + 1시간마다 갱신
  - KRW 마켓만 필터 (KRW-BTC, KRW-ETH, ...)

[2단계: 스크리닝 후보 실시간 모니터링]
  - WebSocket ticker 구독 (전체 KRW 마켓)
  - 거래량/변동성 기준으로 후보 선별

[3단계: 후보 종목 분봉 수집]
  - 선별된 종목만 REST API로 분봉 수집
  - 1분봉 기준, 최근 200개 캔들 유지
  - SQLite에 저장 + 메모리 캐시 (최근 데이터 빠른 접근)
```

### 3.3 종목 스크리닝 기준

```
ScreeningCriteria:
  min_volume_krw:       500,000,000   # 최소 24h 거래대금 5억원
  min_volatility_pct:   1.0           # 최소 변동성 1%
  max_volatility_pct:   15.0          # 최대 변동성 15% (급등락 코인 제외)
  max_coins:            10            # 최대 모니터링 종목 수
  refresh_interval_min: 30            # 30분마다 재스크리닝
```

스크리닝 흐름:
1. 24시간 거래대금 기준 필터
2. 변동성 범위 필터 (너무 낮거나 높은 종목 제외)
3. 거래대금 x 변동성 점수로 정렬
4. 상위 N개 선별
5. 기존 포지션 보유 종목은 스크리닝 대상에서 제외하지 않음 (모니터링 유지)

### 3.4 데이터 저장 스키마

```sql
CREATE TABLE candles (
    market     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    timestamp  INTEGER NOT NULL,
    open       REAL NOT NULL,
    high       REAL NOT NULL,
    low        REAL NOT NULL,
    close      REAL NOT NULL,
    volume     REAL NOT NULL,
    PRIMARY KEY (market, timeframe, timestamp)
);

CREATE TABLE screening_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  INTEGER NOT NULL,
    market     TEXT NOT NULL,
    volume_krw REAL NOT NULL,
    volatility REAL NOT NULL,
    score      REAL NOT NULL
);
```

### 3.5 하네스 적용

- **Context**: `docs/api/upbit-limits.md`에 Upbit API 제한사항 문서화
- **Constraint**: `upbit_client.py`는 `repository/` 직접 의존 금지. 반드시 `service/collector.py`를 통해 저장
- **GC**: 7일 이상 된 1분봉 데이터 자동 정리. 미사용 스크리닝 로그 30일 후 삭제

---

## 4. ML 전략 & 피처 엔지니어링

### 4.1 ML 파이프라인

```
[분봉 데이터] → [피처 엔지니어링] → [학습/예측] → [시그널 생성]
                                                    │
                                             BUY / SELL / HOLD
                                             + confidence score
```

### 4.2 피처 카테고리

**Price Action (가격 기반)**:
- `return_1m`, `return_5m`, `return_15m`, `return_60m`: N분 수익률
- `high_low_ratio`: 고가/저가 비율 (캔들 크기)
- `close_position`: (close - low) / (high - low) — 캔들 내 종가 위치

**Technical Indicators (기술적 지표)**:
- `rsi_14`, `rsi_7`: RSI
- `macd`, `macd_signal`, `macd_hist`: MACD
- `bb_upper`, `bb_lower`, `bb_width`: 볼린저밴드
- `ema_5`, `ema_20`, `ema_60`: EMA 대비 종가 비율

**Volume (거래량)**:
- `volume_ratio_5m`, `volume_ratio_20m`: 평균 거래량 대비 비율
- `volume_trend`: 거래량 증감 추세 (선형 회귀 기울기)
- `buy_sell_ratio`: 매수/매도 체결 비율

**Market Context (시장 컨텍스트)**:
- `btc_return_5m`, `btc_return_60m`: BTC 수익률 (시장 방향)
- `market_volatility`: KRW 마켓 전체 변동성
- `coin_rank_volume`: 거래대금 순위 (상대적 위치)

### 4.3 라벨링 (타겟 변수)

향후 N분 수익률 기반 3-class 분류:
- `BUY`: 향후 수익률 > +threshold
- `HOLD`: -threshold ~ +threshold
- `SELL`: 향후 수익률 < -threshold

설정값 (config/settings.yaml):
```yaml
strategy:
  lookahead_minutes: 5
  threshold_pct: 0.3
  retrain_interval_hours: 6
  min_confidence: 0.6
```

### 4.4 모델 학습

- 시간순 Train/Validation 분할 (Train 80%, Validation 20%). 절대 셔플하지 않음
- LightGBM 기본 사용, XGBoost 비교 실험 가능

모델 저장 구조:
```
data/models/
├── KRW-BTC/
│   ├── model_20260403_1200.pkl
│   └── meta_20260403_1200.json   # 성능 지표, 피처 목록, 학습 기간
├── KRW-ETH/
│   └── ...
└── model_registry.json           # 종목별 현재 활성 모델 매핑
```

### 4.5 실시간 예측

1. 활성 모델 로드 (model_registry에서 조회)
2. 피처 생성 (학습 때와 동일한 `FeatureBuilder` 사용 — Train-Serve Skew 방지)
3. 예측 수행 → predict_proba → [sell, hold, buy]
4. confidence score 산출
5. 최소 신뢰도(0.6) 미달 시 HOLD 반환

### 4.6 모델 재학습 전략

트리거:
- 시간 기반: 6시간마다 정기 재학습
- 성능 기반: 최근 1시간 예측 정확도 < 40% 시 긴급 재학습
- 데이터 기반: 새 캔들 1000개 이상 누적 시

안전장치:
- 신규 모델 validation 성능이 기존보다 낮으면 교체하지 않음
- 재학습 중에도 기존 모델로 예측 계속 (무중단)
- 모델 이력 보관 (롤백 가능)

### 4.7 하네스 적용

- **Context**: `docs/ml/feature-catalog.md` — 전체 피처 목록, 의미, 계산식 문서화
- **Constraint**: `features.py`는 순수 함수(side-effect 없음). DB/API 직접 호출 금지. mypy strict 적용
- **Constraint**: 학습/예측에 동일한 `FeatureBuilder` 단일 클래스 강제 사용
- **GC**: 30일 이상 된 모델 파일 자동 정리. `model_registry.json`과 실제 파일 불일치 감지 & 경고

---

## 5. 가상 매매 엔진 & 리스크 관리

### 5.1 페이퍼 트레이딩 엔진

실제 거래소에 주문을 보내지 않고, Upbit 실시간 시세를 기반으로 가상 체결을 시뮬레이션한다.

```
[Signal] → [Risk Check] → [Paper Engine] → [TradeEvent] → Dashboard
```

### 5.2 가상 계좌 모델

```
PaperAccount:
  initial_balance: 10,000,000 KRW
  cash_balance: 현재 보유 현금
  positions: {market: Position}

Position:
  market, side, entry_price, quantity, entry_time
  unrealized_pnl, highest_price (트레일링 스탑용)

Order:
  id (UUID), market, side, order_type, price, quantity
  status (PENDING/FILLED/CANCELLED)
  signal_confidence, fill_price (슬리피지 반영), fee
```

### 5.3 가상 체결 시뮬레이션

- 슬리피지: 호가 스프레드 기반 0.05% 적용
- 수수료: Upbit 0.05% (매수/매도 각각)
- 최소 주문 금액: 5,000 KRW
- 매수: cash -= (fill_price x quantity) + fee → position 생성
- 매도: cash += (fill_price x quantity) - fee → realized_pnl 계산
- 금액 계산은 반드시 `Decimal` 타입 사용 (float 금지)

### 5.4 리스크 관리 규칙

```
RiskConfig:
  # 포지션 관리
  max_position_pct:         25%     # 종목당 최대
  max_open_positions:       4       # 동시 최대 (25% x 4 = 100%)
  min_order_krw:            5,000   # Upbit 최소 주문

  # 손절 / 익절
  stop_loss_pct:            2%      # 진입가 대비
  take_profit_pct:          5%
  trailing_stop_pct:        1.5%    # 최고가 대비

  # 일일 리스크 한도
  max_daily_loss_pct:       5%
  max_daily_trades:         50

  # 서킷 브레이커
  consecutive_loss_limit:   5       # 연속 손실 시 매매 중지
  cooldown_minutes:         60      # 중지 후 쿨다운
```

### 5.5 리스크 체크 플로우

```
Signal 수신
  → [1] 서킷 브레이커 확인 (연속 손실 >= 5? / 쿨다운 중?)
  → [2] 일일 한도 확인 (금일 손실 >= 5%? / 거래 횟수 >= 50?)
  → [3] 포지션 한도 확인 (보유 종목 >= 4? / 중복 매수?)
  → [4] 포지션 사이징 (min(cash, total x 25%) / 최소 금액 미달?)
  → [5] 주문 생성 → PaperEngine으로 전달
```

### 5.6 포지션 모니터링 (매 틱마다)

매 시세 업데이트마다:
1. 미실현 손익 갱신
2. 최고가 갱신 (트레일링 스탑용)
3. 자동 청산 조건 체크: 손절(-2%) / 익절(+5%) / 트레일링 스탑(최고가 -1.5%)

### 5.7 거래 기록 저장

```sql
CREATE TABLE orders (
    id          TEXT PRIMARY KEY,
    market      TEXT NOT NULL,
    side        TEXT NOT NULL,
    order_type  TEXT NOT NULL,
    price       REAL NOT NULL,
    fill_price  REAL,
    quantity    REAL NOT NULL,
    fee         REAL NOT NULL,
    status      TEXT NOT NULL,
    signal_confidence REAL,
    reason      TEXT,           -- 'ML_SIGNAL' / 'STOP_LOSS' / 'TAKE_PROFIT' / 'TRAILING_STOP'
    created_at  INTEGER NOT NULL,
    filled_at   INTEGER
);

CREATE TABLE daily_summary (
    date             TEXT PRIMARY KEY,
    starting_balance REAL NOT NULL,
    ending_balance   REAL NOT NULL,
    realized_pnl     REAL NOT NULL,
    total_trades     INTEGER NOT NULL,
    win_trades       INTEGER NOT NULL,
    loss_trades      INTEGER NOT NULL,
    max_drawdown_pct REAL NOT NULL
);
```

### 5.8 하네스 적용

- **Context**: `docs/trading/risk-rules.md` — 리스크 규칙과 근거 문서화
- **Constraint**: 금액 계산에 `Decimal` 강제, `float` 사용 시 mypy 에러 + 구조적 테스트 실패
- **Constraint**: `PaperEngine.execute_order()`는 `RiskManager.approve()` 통과 후에만 호출 가능. 구조적 테스트로 강제
- **GC**: 90일 이상 된 주문 기록 아카이브. `daily_summary`와 `orders` 간 정합성 주기적 검증

---

## 6. 웹 대시보드

### 6.1 기술 스택

- Backend: FastAPI (WebSocket 지원, 비동기)
- Frontend: React + Vite + Recharts
- 통신: REST (초기 로드) + WebSocket (실시간 업데이트)
- 테마: 다크 테마 (트레이딩 UI 표준)

### 6.2 페이지 구성

**메인 대시보드** `/`:
- 요약 카드: 총 자산 / 현금 잔고 / 수익률 / 금일 PnL
- 자산 추이 차트 (라인 차트, 시간별)
- 보유 포지션 테이블 (실시간 미실현 손익)
- 최근 거래 내역 (10건)

**포트폴리오** `/portfolio`:
- 자산 배분 파이 차트 (현금 vs 종목별)
- 종목별 수익률 바 차트
- 전체 거래 이력 (필터/정렬/페이징)
- 일별 수익률 히트맵

**전략 모니터** `/strategy`:
- 스크리닝 현황 (현재 모니터링 중인 종목)
- 종목별 실시간 차트 + 매수/매도 시그널 마커
- ML 모델 상태 (정확도, 마지막 학습 시각, 피처 중요도)
- 시그널 로그 (BUY/SELL/HOLD + confidence)

**리스크** `/risk`:
- 일일 손실 현황 (한도 대비 게이지)
- 서킷 브레이커 상태
- 연속 손실 카운터
- 리스크 이벤트 로그 (REJECT 사유 포함)

**설정** `/settings`:
- 시드머니 / 종목당 비율 변경
- 리스크 파라미터 조정
- 스크리닝 기준 변경
- 매매 일시 중지 / 재개 토글

### 6.3 API 엔드포인트

REST:
```
GET   /api/dashboard/summary
GET   /api/portfolio/positions
GET   /api/portfolio/history?page=1&size=20
GET   /api/portfolio/daily
GET   /api/strategy/screening
GET   /api/strategy/signals
GET   /api/strategy/model-status
GET   /api/risk/status
GET   /api/candles/{market}
PUT   /api/settings
POST  /api/control/pause
POST  /api/control/resume
```

WebSocket:
```
WS /ws/live
  → { type: "price_update",    data: { market, price, change_pct } }
  → { type: "position_update", data: { market, unrealized_pnl } }
  → { type: "trade_executed",  data: { order details } }
  → { type: "signal_fired",    data: { market, signal, confidence } }
  → { type: "risk_alert",      data: { reason, details } }
  → { type: "summary_update",  data: { total_equity, daily_pnl } }
```

### 6.4 실시간 데이터 흐름

```
[EventBus] → [FastAPI WebSocket 브로드캐스트] → [React 상태 업데이트]
```

5초마다 summary 데이터 자동 푸시.

### 6.5 하네스 적용

- **Context**: `docs/api/dashboard-endpoints.md` — API 명세 문서화
- **Constraint**: UI 레이어는 비즈니스 로직 직접 호출 금지. REST/WebSocket API 통해서만 접근. `ui/` 내부에서 `service/`, `repository/` import 시 CI 실패
- **Constraint**: WebSocket 메시지 타입은 `types/` 레이어의 Enum으로 정의. `docs/api/ws-schema.json` 공유
- **GC**: 미사용 API 엔드포인트 감지. 프론트엔드에서 호출하지 않는 엔드포인트 식별 & 경고

---

## 7. 테스트 전략 & CI/CD

### 7.1 테스트 피라미드

```
         ╱  E2E (2~3개)  ╲           브라우저 대시보드 → 가상매매 흐름
        ╱─────────────────╲
       ╱  통합 테스트 (20%) ╲         모듈 간 이벤트 흐름, DB 연동
      ╱─────────────────────╲
     ╱   단위 테스트 (70%)    ╲       피처 계산, 리스크 체크, 체결 로직
    ╱─────────────────────────╲
   ╱   구조적 테스트 (필수)      ╲     레이어 의존성, 타입 강제
  ╱─────────────────────────────╲
```

### 7.2 구조적 테스트 (하네스의 핵심)

- `test_no_upward_dependency`: 상위 레이어 import 위반 감지
- `test_decimal_in_financial_modules`: paper_engine, risk_manager, portfolio에서 float 리터럴 사용 금지
- `test_risk_manager_gate`: PaperEngine 호출 전 RiskManager.approve 강제

### 7.3 단위 테스트

| 모듈 | 테스트 대상 |
|------|-----------|
| `test_features.py` | RSI, MACD, BB 계산값 검증, 경계 조건, 결정론적 출력 |
| `test_screener.py` | 거래량/변동성 필터, 상위 N개 선별, 빈 마켓 처리 |
| `test_paper_engine.py` | 매수/매도 체결, 슬리피지, 수수료, 잔고 부족 거부 |
| `test_risk_manager.py` | 25% 한도, 일일 손실, 서킷 브레이커, 연속 손실 카운팅 |
| `test_predictor.py` | 최소 신뢰도 미달 → HOLD, 모델 미존재 예외 |
| `test_portfolio.py` | 손절/익절/트레일링 스탑, 미실현 PnL, 최고가 갱신 |

### 7.4 통합 테스트

- `test_signal_to_trade.py`: Signal → RiskCheck → PaperEngine → DB 저장
- `test_screening_to_collection.py`: 스크리닝 결과 → 해당 종목 분봉 수집 시작
- `test_retrain_cycle.py`: 캔들 축적 → 재학습 트리거 → 모델 교체 → 예측 계속
- `test_event_flow.py`: EventBus 통한 모듈 간 이벤트 전달 검증

### 7.5 CI 파이프라인

```
Stage 1 (30초): ruff lint + ruff format + mypy strict
Stage 1 (30초): structural tests (레이어 규칙)
Stage 2 (1~2분): 단위 테스트 (pytest --cov)
Stage 3 (2~3분): 통합 테스트
```

Stage 1 두 job은 병렬 실행. Stage 2는 Stage 1 통과 후. Stage 3은 Stage 2 통과 후.

### 7.6 Pre-commit 훅

- ruff check (lint)
- ruff format (format)
- mypy --strict (type check)
- pytest tests/structural/ (레이어 의존성 검증)

### 7.7 품질 감사 (GC 축)

`scripts/quality_audit.py` — 주기적 실행 (수동 또는 CI 주 1회):
- 미사용 함수/변수 감지
- 문서 ↔ 코드 불일치 확인
- 모델 레지스트리 ↔ 파일 정합성
- 오래된 캔들/주문 정리 대상 식별
- 네이밍 컨벤션 준수 확인

---

## 8. AGENTS.md 명세

60줄 이하로 유지. 에이전트용 목차 역할.

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

---

## 9. 주요 의존성

```
# Python (Backend)
python = ">=3.12"
uvicorn = "*"
fastapi = "*"
websockets = "*"
pydantic = "*"
pydantic-settings = "*"
httpx = "*"                 # Upbit REST API 호출
lightgbm = "*"
xgboost = "*"
scikit-learn = "*"
pandas = "*"
numpy = "*"
ta = "*"                    # 기술적 지표 라이브러리
joblib = "*"                # 모델 직렬화
aiosqlite = "*"             # 비동기 SQLite
pyyaml = "*"

# Dev
pytest = "*"
pytest-asyncio = "*"
pytest-cov = "*"
ruff = "*"
mypy = "*"
pre-commit = "*"

# Frontend
react = "^19"
vite = "*"
recharts = "*"              # 차트
react-router-dom = "^7"
```
