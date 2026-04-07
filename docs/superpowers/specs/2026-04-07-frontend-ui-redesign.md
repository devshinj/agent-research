# Frontend UI Redesign

## Problem

현재 6개 페이지(대시보드, 차트, 포트폴리오, 전략, 리스크, 설정)가 역할이 불분명하고 데이터가 중복된다.

- 포지션 테이블이 대시보드/포트폴리오에 중복
- 차트 페이지가 캔들차트만 보여주는데 별도 메뉴
- 설정/리스크/전략에서 config 편집이 흩어져 혼란
- 설정에서 매매 엔진 제어 + 파라미터 편집이 결합

## Decisions

| 질문 | 결정 |
|------|------|
| 대시보드 역할 | 메인 콕핏 — 포지션 상세, 거래내역, 차트까지 한 화면 |
| 설정 편집 방식 | 하이브리드 — 각 페이지에서 인라인 편집, "시스템" 페이지는 엔진 제어 전용 |
| 페이지 구성 | 6개 → 4개 (대시보드, 전략, 리스크, 시스템) |
| 대시보드 레이아웃 | 세로 스크롤 + 포지션 행 클릭 시 캔들차트 아코디언 펼침 |

---

## Architecture

### Page Structure (6 → 4)

```
Before:                          After:
├── 대시보드                      ├── 대시보드 (메인 콕핏)
├── 차트          ──────┐         │   ├── KPI 카드
├── 포트폴리오    ──────┤─→       │   ├── 자산추이 차트
├── 전략                │         │   ├── 포지션 테이블 (행 클릭 → 캔들차트 펼침)
├── 리스크              │         │   └── 거래내역
└── 설정                │         ├── 전략
                        │         │   ├── 스크리닝 결과
                        │         │   ├── 활성 신호 + SHAP
                        │         │   ├── 모델 상태
                        │         │   └── 전략 설정 인라인 편집
                        │         ├── 리스크
                        │         │   ├── 서킷브레이커 상태
                        │         │   ├── 리스크 지표 카드
                        │         │   └── 리스크/매매 설정 인라인 편집
                        │         └── 시스템 (설정 → 이름 변경)
                        │             ├── 매매 시작/중지
                        │             ├── 일시정지/재개
                        │             ├── 전체 초기화 (위험 작업)
                        │             └── 비편집 필드 조회 (DB경로, 모델경로 등)
```

### Routing

| Path | Component | 설명 |
|------|-----------|------|
| `/` | Dashboard | 메인 콕핏 |
| `/strategy` | Strategy | 전략 + ML + 인라인 설정 |
| `/risk` | Risk | 리스크 + 인라인 설정 |
| `/system` | System | 엔진 제어 전용 |

### Sidebar

```
CRYPTO PAPER TRADER
Upbit ML Strategy v0.1

[대시보드]
[전략]
[리스크]
[시스템]

[매매 시작/중지 토글]
● 실시간 / 오프라인
```

---

## Component Design

### 1. Dashboard (메인 콕핏)

세로 스크롤 레이아웃. 기존 Dashboard + Portfolio + Charts를 통합.

**섹션 순서:**

1. **KPI 카드 (4칸 그리드)** — 총 평가 자산(매매 상태 배지 포함), 투자 가능 금액, 총 평가 손익, 총 수익률. 기존 Dashboard 그대로.

2. **자산추이 차트** — 기간 전환 버튼(24h/1일/1주/1개월). 기존 Dashboard의 AreaChart 그대로.

3. **포지션 테이블** — 기존 Portfolio의 상세 테이블 베이스.
   - 컬럼: 코인, 평단가, 현재가, 손익, 수익률, 수량, 총 투자금, 평가금액, 상태
   - **행 클릭 → 아래로 캔들차트 아코디언 펼침** (기존 Charts.tsx의 lightweight-charts)
   - 한 번에 하나만 펼침 (다른 행 클릭 시 이전 닫힘)
   - 포지션 없을 때 empty state 표시

4. **거래내역** — 기존 Portfolio의 거래내역 테이블 + 페이지네이션 그대로.

**데이터 소스:**
- `/api/dashboard/summary` (30초 폴링 + WebSocket)
- `/api/portfolio/positions` (30초 폴링)
- `/api/portfolio/daily?period=` (기간 변경 시)
- `/api/dashboard/candles?market=&limit=100` (포지션 행 클릭 시 on-demand)
- `/api/portfolio/history?page=&size=20` (거래내역)

### 2. Strategy (전략 + 인라인 설정)

기존 Strategy.tsx에 전략 관련 설정 인라인 편집을 추가.

**섹션 순서:**

1. **스크리닝 결과** — 기존 그대로
2. **활성 신호** — 기존 그대로 (SHAP 툴팁 포함)
3. **모델 상태** — 기존 그대로
4. **전략 설정 (신규)** — 인라인 편집 패널
   - **스크리닝 설정**: min_volume_krw, min/max_volatility_pct, max_coins, refresh_interval_min, always_include
   - **ML 전략 설정**: lookahead_minutes, threshold_pct, retrain_interval_hours, min_confidence
   - **진입 분석 설정**: min_entry_score, price_lookback_candles
   - hot-reload 가능 필드는 슬라이더/인풋, 불가 필드는 읽기전용 표시
   - "적용" 버튼 → PATCH `/api/control/config`

### 3. Risk (리스크 + 인라인 설정)

기존 Risk.tsx를 확장. 리스크 지표 + 매매/리스크 설정 인라인 편집.

**섹션 순서:**

1. **서킷브레이커 상태** — 기존 그대로
2. **리스크 지표 카드** — 기존 3칸 그리드 그대로 (일일 손실, 연속 손실, 일일 거래)
3. **리스크 설정 (확장)** — 기존 슬라이더 + 추가 필드
   - **리스크**: stop_loss_pct, take_profit_pct, trailing_stop_pct, max_daily_trades, consecutive_loss_limit, cooldown_minutes, partial_take_profit_pct, partial_sell_fraction
   - **매매**: max_position_pct, max_open_positions, max_additional_buys, additional_buy_drop_pct, additional_buy_ratio
   - 슬라이더 UI 유지, "적용"/"초기화" 버튼

### 4. System (시스템 제어 전용)

기존 Settings.tsx를 축소. 매매 엔진 제어 + 비편집 필드 조회.

**섹션:**

1. **매매 엔진 제어** — 매매 시작/중지, 일시정지/재개 버튼
2. **전체 초기화** — 경고 문구 + 확인 모달. 초기 잔고, fee_rate, slippage_rate, min_order_krw 등 비-hot-reload 필드 편집 가능.
3. **시스템 정보** — DB 경로, 모델 디렉토리, 캔들 주기 등 읽기전용 조회
4. **버전 정보** — 기존 About 섹션

---

## Data Flow

```
                    ┌─────────────┐
                    │  useApi()   │ ← REST 호출 공통 훅
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   Dashboard           Strategy            Risk
   (positions,         (screening,        (risk status,
    summary,            signals,           config PATCH)
    candles,            model-status,
    history)            config PATCH)
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                      System (pause/resume/reset)
```

- 설정 변경(PATCH)은 전략/리스크 페이지에서 각각 담당하는 섹션만 관리
- System 페이지는 POST /control/pause, /control/resume, /control/reset, /control/trading/start|stop만 사용
- 설정 편집 후 PATCH 응답으로 최신 config가 돌아오므로, 페이지 간 동기화 문제 없음

## Deleted Files

- `pages/Charts.tsx` — 대시보드로 흡수
- `pages/Portfolio.tsx` — 대시보드로 흡수

## Modified Files

| File | Changes |
|------|---------|
| `App.tsx` | 라우트 4개로 축소, 사이드바 메뉴 4개, Charts/Portfolio import 제거 |
| `pages/Dashboard.tsx` | Portfolio + Charts 통합. 포지션 아코디언 차트, 거래내역 추가 |
| `pages/Strategy.tsx` | 하단에 전략 설정 인라인 편집 패널 추가 (screening, strategy, entry_analyzer) |
| `pages/Risk.tsx` | 슬라이더에 리스크/매매 설정 필드 추가 (stop_loss_pct 등) |
| `pages/Settings.tsx` → `pages/System.tsx` | 리네임. 설정 편집 UI 제거, 엔진 제어 + 초기화 + 읽기전용 정보로 축소 |

## Testing

- TypeScript tsc --noEmit 통과
- Vite build 성공
- 각 페이지 렌더링 확인 (빈 데이터 + 더미 데이터)
- 설정 PATCH 후 반영 확인
- 포지션 행 클릭 → 차트 펼침/닫힘 동작
- 매매 시작/중지 토글 동작
- 전체 초기화 플로우 (모달 → 확인 → 리셋)
