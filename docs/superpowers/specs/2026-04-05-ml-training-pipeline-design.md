# ML Training Pipeline Design

## Problem

캔들 데이터는 정상 수집되지만, 학습된 ML 모델이 없어 거래가 발생하지 않음.
`Predictor.predict()`가 `KeyError`를 raise하고 `App`에서 조용히 무시되는 상태.

## Solution

`Trainer` 서비스 클래스를 추가하여 수집된 캔들 데이터로 LightGBM 모델을 학습하고,
App 시작 시 자동 로드 + 6시간 주기 재학습을 수행한다.

## Labeling Strategy

- **Lookahead**: 5분 (`settings.strategy.lookahead_minutes`)
- **수식**: `future_return = close.shift(-lookahead) / close - 1`
- **분류**:
  - `future_return >= +0.3%` → BUY (class 2)
  - `future_return <= -0.3%` → SELL (class 0)
  - 그 사이 → HOLD (class 1)
- **Threshold**: `settings.strategy.threshold_pct` (0.3%)
- `Predictor`의 `LABEL_TO_SIGNAL = {0: SELL, 1: HOLD, 2: BUY}`와 일치

## Trainer Class (`src/service/trainer.py`)

```python
class Trainer:
    def __init__(
        self,
        feature_builder: FeatureBuilder,
        candle_repo: CandleRepository,
        model_dir: Path,
        lookahead_minutes: int,
        threshold_pct: float,
    ) -> None: ...

    def label(self, df: pd.DataFrame) -> pd.Series:
        """5분 후 변동률 기반 BUY/HOLD/SELL 라벨 생성."""

    async def train(self, market: str, timeframe: str) -> Path | None:
        """단일 마켓 학습. 데이터 부족 시 None 반환."""

    async def train_all(self, markets: list[str], timeframe: str) -> dict[str, Path]:
        """여러 마켓 일괄 학습. {market: model_path} 반환."""
```

### Data Flow

```
candle_repo.get_latest(market, "1m", limit=2000)
    ↓
DataFrame (OHLCV)
    ↓
trainer.label(df) → target Series (0/1/2)
    ↓
feature_builder.build(df) → features DataFrame (20 columns)
    ↓
유효 행 필터 (NaN 제거, lookahead 잘림 제거)
    ↓
< 500 유효행이면 스킵, None 반환
    ↓
LightGBM 학습 (multiclass, 3 classes)
    ↓
joblib.dump → data/models/{market}.joblib
    ↓
Path 반환
```

### Minimum Data Requirement

- 최소 500개 유효 샘플 (NaN 제거 + lookahead 잘림 후 기준)
- 캔들 기준 약 560개 이상 필요 (피처 빌드에 ~60개 소모)
- 약 8시간 이상 수집 후 학습 가능

### LightGBM Parameters

```python
{
    "objective": "multiclass",
    "num_class": 3,
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "verbosity": -1,
}
```

보수적 기본값. 작은 데이터셋 과적합 방지 우선.

## App Integration (`src/runtime/app.py`)

### 시작 시 (App.start)

1. `data/models/` 디렉토리 스캔 → 기존 `.joblib` 파일을 `predictor.load_model()`로 로드
2. 스크리닝 실행
3. 모델 없는 스크린된 마켓에 대해 `trainer.train()` 호출
4. 학습 성공 시 `predictor.load_model()` 즉시 등록

### 주기적 재학습

- `scheduler.schedule_interval("retrain", _retrain, interval_seconds=retrain_interval_hours * 3600)`
- `_retrain()`:
  1. 스크린된 마켓 전체에 대해 `trainer.train_all()` 호출
  2. 새로 생성된 모델을 `predictor.load_model()`로 핫 리로드
  3. 학습 결과 로깅 (성공/스킵 마켓 수)

### paused 상태

- `self.paused == True`이면 재학습도 스킵 (기존 패턴과 동일)

## File Changes

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `src/service/trainer.py` | 신규 | Trainer 클래스 |
| `src/runtime/app.py` | 수정 | 시작 시 모델 로드/학습, 재학습 스케줄 등록 |
| `pyproject.toml` | 수정 | `lightgbm` 의존성 추가 |
| `tests/structural/test_trainer.py` | 신규 | Trainer 구조 테스트 |

### 변경 없는 파일

- `src/service/predictor.py` — 기존 `load_model()` / `predict()` 그대로 사용
- `src/service/features.py` — `FeatureBuilder.build()` 그대로 사용
- `src/service/risk_manager.py` — 변경 없음
- `src/config/settings.py` — 기존 `strategy.lookahead_minutes`, `threshold_pct`, `retrain_interval_hours`, `data.model_dir` 활용

## Layer Compliance

- `Trainer`는 service 레이어 → repository 레이어(`CandleRepository`) 의존: OK
- `Trainer`는 service 레이어 → types 레이어(`FeatureBuilder`) 의존: OK
- `App`은 runtime 레이어 → service 레이어(`Trainer`, `Predictor`) 의존: OK
- 역방향 의존 없음
