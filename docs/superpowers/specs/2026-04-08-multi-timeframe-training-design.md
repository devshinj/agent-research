# Multi-Timeframe Collection & Training Pipeline Improvement

## Problem

현재 시스템은 1분봉 500개(~8시간)만으로 학습하며, 라벨 불균형 처리가 없어 모델이 항상 HOLD만 출력한다.

### 근본 원인
1. **데이터 부족**: 8시간치 1분봉으로는 BUY 라벨이 극소수
2. **Feature 정보 부족**: 최대 1시간 EMA까지 — 장기 추세 정보 없음
3. **라벨 불균형 미처리**: `scale_pos_weight` 없이 학습 → "항상 HOLD"가 최적 전략으로 수렴
4. **검증 지표 부적절**: accuracy만 측정 (99% HOLD → 99% accuracy)

## Solution

### 1. Multi-Timeframe Collection

3개 타임프레임을 각각 수집하여 DB에 누적 저장한다.

| Timeframe | Count | Coverage | Interval | API Calls | Purpose |
|-----------|-------|----------|----------|-----------|---------|
| 1m        | 500   | ~8h      | 60s      | 3         | Prediction (entry timing) |
| 15m       | 960   | ~10d     | 15min    | 5         | Training (main data) |
| 1D        | 30    | ~30d     | 1h       | 1         | Context features |

- DB 스키마 변경 없음 (이미 `timeframe` 컬럼 존재)
- 중복은 `ON CONFLICT DO UPDATE` (UPSERT)로 처리됨

### 2. Settings Changes

```yaml
collector:
  candle_timeframe: 1          # 기존 유지 (예측용 1분봉)
  max_candles_per_market: 500  # 기존 유지
  train_timeframe: 15          # NEW: 학습용 15분봉
  train_candles: 960           # NEW: 10일치
  daily_candles: 30            # NEW: 일봉 30일치
  market_refresh_interval_min: 60
```

`CollectorConfig` dataclass에 3개 필드 추가:
- `train_timeframe: int = 15`
- `train_candles: int = 960`
- `daily_candles: int = 30`

### 3. Collector Changes

`collector.py`에 `collect_train_candles()` 메서드 추가:

```python
async def collect_train_candles(self, markets: list[str]) -> None:
    """15분봉 + 일봉 수집 (학습용)"""
    for market in markets:
        # 15분봉
        candles_15m = await self._client.fetch_candles(
            market, self._train_timeframe, self._train_candles
        )
        if candles_15m:
            await self._repo.save_many(candles_15m, commit=False)

        # 일봉
        candles_daily = await self._client.fetch_daily_candles(
            market, self._daily_candles
        )
        if candles_daily:
            await self._repo.save_many(candles_daily, commit=False)

        await asyncio.sleep(0.11)
    await self._repo.commit()
```

Constructor에 `train_timeframe`, `train_candles`, `daily_candles` 파라미터 추가.

### 4. FeatureBuilder Changes

기존 `build()` 메서드는 변경 없음. 새 메서드 추가:

```python
def build_daily_context(self, daily_df: pd.DataFrame) -> pd.Series:
    """일봉 DataFrame에서 최신 context feature 1행을 반환한다."""
```

일봉 기반 6개 feature:
- `daily_rsi_14`: 일봉 RSI(14)
- `daily_ema_5_ratio`: close / EMA(5) - 1
- `daily_ema_20_ratio`: close / EMA(20) - 1
- `daily_volume_ratio`: 당일 volume / rolling(5).mean()
- `daily_trend`: EMA(5) 기울기 → 1(상승), 0(횡보), -1(하락)
- `daily_atr_ratio`: (high-low) / ATR(14)

이 6개 값은 단일 행(최신 일봉 기준)으로 반환되며, 학습/예측 시 모든 행에 broadcast된다 (일봉은 하루 동안 일정).

`get_feature_names()`에 6개 추가 → 총 30개.

### 5. Trainer Changes

#### 5a. 데이터 소스 변경
- 학습: 15분봉 DataFrame + 일봉 context
- `_create_labels()`: `lookahead=4` (4 × 15min = 1시간 후 수익률)

#### 5b. 라벨 불균형 대응
```python
n_hold = (labels == 0).sum()
n_buy = (labels == 1).sum()
scale_pos_weight = n_hold / max(n_buy, 1)

model = lgb.LGBMClassifier(
    scale_pos_weight=scale_pos_weight,
    ...
)
```

#### 5c. Early Stopping
```python
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
)
```

#### 5d. 검증 지표
```python
from sklearn.metrics import f1_score, precision_score, recall_score

val_f1 = f1_score(y_val, val_pred, zero_division=0)
val_precision = precision_score(y_val, val_pred, zero_division=0)
val_recall = recall_score(y_val, val_pred, zero_division=0)
```

메타데이터에 `f1`, `precision`, `recall`, `buy_ratio` 추가 저장.

#### 5e. Train 메서드 시그니처 변경
```python
def train(self, market: str, candle_df: pd.DataFrame,
          daily_df: pd.DataFrame | None = None) -> dict[str, Any]:
```

`daily_df`가 제공되면 `build_daily_context()`로 context feature를 생성하여 feature DataFrame에 합류.

### 6. Predictor Changes

`predict()` 시그니처 변경:
```python
def predict(self, market: str, candle_df: pd.DataFrame,
            daily_df: pd.DataFrame | None = None) -> tuple[Signal, SignalBasis]:
```

예측 시:
1. 1분봉 → `build()` → 24 features
2. 일봉 → `build_daily_context()` → 6 daily features (broadcast)
3. 합쳐서 30 features → `model.predict_proba()`

### 7. App.py Changes

#### 7a. Collector 초기화
```python
self.collector = Collector(
    upbit_client=self.upbit_client,
    candle_repo=self.candle_repo,
    timeframe=settings.collector.candle_timeframe,
    max_candles=settings.collector.max_candles_per_market,
    train_timeframe=settings.collector.train_timeframe,
    train_candles=settings.collector.train_candles,
    daily_candles=settings.collector.daily_candles,
)
```

#### 7b. 스케줄러 태스크 추가
```python
# 기존: 60초마다 1분봉 수집 + 예측
self.scheduler.add("collect_candles", self._collect_and_predict, interval_seconds=60)

# NEW: 15분마다 15분봉 + 일봉 수집
self.scheduler.add("collect_train_data", self._collect_train_data, interval_seconds=900)
```

#### 7c. 학습/예측에 일봉 전달
`_train_missing_models()`, `_retrain()`:
- 15분봉 조회: `candle_repo.get_latest(market, "15m", 960)`
- 일봉 조회: `candle_repo.get_latest(market, "1D", 30)`
- `trainer.train(market, df_15m, daily_df=df_daily)`

`_collect_and_predict()`:
- 1분봉 기반 예측 유지
- 일봉 조회 추가: `candle_repo.get_latest(market, "1D", 30)`
- `predictor.predict(market, df_1m, daily_df=df_daily)`

### 8. Backward Compatibility

- 기존 1분봉 수집/예측 루프 그대로 유지
- 기존 모델 `.pkl` 파일: feature 수 불일치(24 vs 30)로 `predictor.load_model()`에서 자동 스킵 → 다음 retrain에서 새 모델 생성
- DB 스키마 변경 없음
- `daily_df=None` 기본값으로 호출 시 기존 동작과 동일 (일봉 없이 동작 가능)

### 9. File Change Summary

| File | Change |
|------|--------|
| `config/settings.yaml` | `collector` 섹션에 `train_timeframe`, `train_candles`, `daily_candles` 추가 |
| `src/config/settings.py` | `CollectorConfig`에 3개 필드 추가 |
| `src/service/collector.py` | `collect_train_candles()` 메서드 추가, constructor 파라미터 추가 |
| `src/service/features.py` | `build_daily_context()` 메서드 추가, `get_feature_names()` 6개 추가 |
| `src/service/trainer.py` | scale_pos_weight, early stopping, F1, 15분봉+일봉 학습 |
| `src/service/predictor.py` | `predict()` 에 `daily_df` 파라미터 추가 |
| `src/runtime/app.py` | 15분봉/일봉 수집 스케줄, 학습/예측 플로우 변경 |
