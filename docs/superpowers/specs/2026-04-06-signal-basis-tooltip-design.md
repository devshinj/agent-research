# Signal Basis Tooltip Design

## Overview

활성 신호 테이블의 각 행에 hover 시 툴팁으로 해당 신호의 근거를 표시한다. LightGBM의 내장 TreeSHAP contribution을 사용하여 개별 예측에 가장 영향을 미친 Top 5 피처의 이름, SHAP 기여도, 실제 값을 보여준다.

## Scope

### In scope

- `Predictor.predict()`에서 SHAP contribution 계산 (LightGBM `predict(pred_contrib=True)`)
- `SignalBasis` 데이터클래스 추가 (top 5 피처, SHAP 값, 피처 값)
- `signals` DB 테이블에 `basis` TEXT 컬럼 추가 (JSON)
- `SignalRepository.save()`, `get_recent()`에 basis 필드 추가
- `GET /api/strategy/signals` 응답에 `basis` 필드 추가
- Strategy.tsx 활성 신호 행에 CSS hover 툴팁
- 피처 한글 라벨 매핑

### Out of scope

- shap 패키지 설치 (LightGBM 내장 기능 사용)
- 글로벌 feature importance 표시
- SHAP 시각화 차트

## Backend Changes

### 1. `SignalBasis` 데이터클래스 (`src/types/models.py`)

```python
@dataclass(frozen=True)
class SignalBasis:
    top_features: tuple[tuple[str, float, float], ...]
    # Each tuple: (feature_name, shap_value, feature_value)
```

### 2. `Predictor.predict()` 확장 (`src/service/predictor.py`)

반환 타입을 `tuple[Signal, SignalBasis]`로 변경.

SHAP 계산 흐름:
1. `model.predict(latest, pred_contrib=True)` 호출 → shape `(1, n_features+1, n_classes)` 배열 반환
2. 예측된 클래스 (`pred_class`)의 기여도 슬라이스를 추출
3. 마지막 원소(bias term) 제거
4. 절대값 기준 Top 5 피처 인덱스 추출
5. 해당 피처의 (이름, SHAP 값, 실제 값)을 `SignalBasis`에 담아 반환

HOLD 시그널의 경우 빈 `SignalBasis(top_features=())`를 반환.

### 3. `signals` 테이블 확장 (`src/repository/database.py`)

```sql
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    timestamp   INTEGER NOT NULL,
    outcome     TEXT,
    basis       TEXT
);
```

`basis` 컬럼: JSON 문자열, nullable. 기존 데이터와 호환.

### 4. `SignalRepository` 확장 (`src/repository/signal_repo.py`)

- `save()`: `basis` 파라미터 추가 (`str | None`), INSERT에 포함
- `get_recent()`: SELECT에 `basis` 포함, 반환 dict에 `basis` 키 추가 (JSON 문자열 그대로)

### 5. `App._collect_and_predict()` 수정 (`src/runtime/app.py`)

```python
signal, basis = self.predictor.predict(market, df)
basis_json = json.dumps([
    {"feature": f, "shap": round(s, 4), "value": round(v, 4)}
    for f, s, v in basis.top_features
]) if basis.top_features else None
await self.signal_repo.save(
    signal.market, signal.signal_type.name,
    signal.confidence, signal.timestamp, basis_json,
)
```

### 6. API 응답 확장 (`src/ui/api/routes/strategy.py`)

`GET /api/strategy/signals` 응답에 `basis` 추가:

```python
{
    "market": r["market"],
    "signal_type": r["signal_type"],
    "confidence": r["confidence"],
    "created_at": "...",
    "basis": json.loads(r["basis"]) if r["basis"] else None,
}
```

## Frontend Changes

### 1. 피처 한글 라벨 매핑 (Strategy.tsx 내 상수)

```typescript
const FEATURE_LABELS: Record<string, string> = {
  return_1m: "1분 수익률",
  return_5m: "5분 수익률",
  return_15m: "15분 수익률",
  return_60m: "60분 수익률",
  high_low_ratio: "고저 비율",
  close_position: "종가 위치",
  rsi_14: "RSI(14)",
  rsi_7: "RSI(7)",
  macd: "MACD",
  macd_signal: "MACD 시그널",
  macd_hist: "MACD 히스토그램",
  bb_upper: "볼린저 상단",
  bb_lower: "볼린저 하단",
  bb_width: "볼린저 폭",
  ema_5_ratio: "EMA(5) 비율",
  ema_20_ratio: "EMA(20) 비율",
  ema_60_ratio: "EMA(60) 비율",
  volume_ratio_5m: "거래량(5분)",
  volume_ratio_20m: "거래량(20분)",
  volume_trend: "거래량 추세",
};
```

### 2. Signal 인터페이스 확장

```typescript
interface BasisEntry {
  feature: string;
  shap: number;
  value: number;
}

interface Signal {
  market: string;
  signal_type: string;
  confidence: number;
  created_at: string;
  basis: BasisEntry[] | null;
}
```

### 3. 툴팁 UI

CSS hover 툴팁. 신호 행에 마우스를 올리면 하단에 근거 카드가 나타남.

```
┌──────────────────────────────────────────────────────────────┐
│ 시간          코인       신호    신뢰도                       │
│ 15:30:00     KRW-BTC    BUY    ████████░░ 82%               │
│  ┌─────────────────────────────────────┐                    │
│  │ 신호 근거                            │                    │
│  │ ↑ RSI(14)           72.3    +0.15   │                    │
│  │ ↑ 거래량(5분)        2.4x    +0.12   │                    │
│  │ ↑ MACD 히스토그램    0.003   +0.08   │                    │
│  │ ↓ 볼린저 상단       -0.02   -0.05   │                    │
│  │ ↑ EMA(5) 비율        0.01   +0.04   │                    │
│  └─────────────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────┘
```

각 행:
- 방향 화살표: SHAP > 0이면 ↑ (매수 방향 기여), < 0이면 ↓ (매도 방향 기여)
- 피처 한글 라벨
- 실제 값 (소수점 4자리)
- SHAP 기여도 (±부호 포함)

basis가 null이면 툴팁 표시하지 않음.

### 4. CSS 툴팁 스타일 (`index.css`)

`position: relative`로 행에 배치, `position: absolute`로 툴팁 패널 표시. hover 시 `opacity` 전환으로 부드럽게 나타남.

## API Contract

### Response

```json
GET /api/strategy/signals?limit=50

[
  {
    "market": "KRW-BTC",
    "signal_type": "BUY",
    "confidence": 0.82,
    "created_at": "2026-04-06 15:30:00",
    "basis": [
      {"feature": "rsi_14", "shap": 0.15, "value": 72.3},
      {"feature": "volume_ratio_5m", "shap": 0.12, "value": 2.4},
      {"feature": "macd_hist", "shap": 0.08, "value": 0.003},
      {"feature": "bb_upper", "shap": -0.05, "value": -0.02},
      {"feature": "ema_5_ratio", "shap": 0.04, "value": 0.01}
    ]
  }
]
```

## Testing

- `Predictor.predict()` 반환 타입 변경: `Signal`과 `SignalBasis` 동시 반환 확인
- SHAP contribution에서 Top 5 추출 정확성 확인
- HOLD 시그널의 경우 빈 `SignalBasis` 반환 확인
- `SignalRepository.save()` / `get_recent()`에 basis JSON 저장/조회 확인
- API 응답에 basis 필드 포함 확인
- 프론트엔드 빌드 성공 확인

## LightGBM pred_contrib 참고

`LGBMClassifier.predict(data, pred_contrib=True)`는 multiclass인 경우:
- 반환 shape: `(n_samples, (n_features + 1) * n_classes)` — flat array
- reshape: `contrib.reshape(n_samples, n_classes, n_features + 1)` 으로 변환
- 각 클래스별 `n_features` 개의 기여도 + 1개의 bias term
- 예측 클래스의 기여도 슬라이스에서 bias를 제외한 값을 사용

이 시스템은 3-class (SELL=0, HOLD=1, BUY=2) 분류이므로 `n_classes=3`, 피처 20개.
- flat shape: `(1, (20 + 1) * 3)` = `(1, 63)`
- reshape 후: `(1, 3, 21)` → `[0, pred_class, :20]`이 해당 클래스의 피처별 SHAP 기여도
