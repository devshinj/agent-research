# 7-Timeframe 60-Feature Training Pipeline

## Problem

현재 15분봉 메인 + 일봉 context(30 features)로는 여전히 데이터 부족 및 제한된 시간축 정보. 7개 타임프레임을 전부 수집하고 각각에서 context feature를 추출하여 60-feature 모델을 학습한다.

## Solution

### 1. Collection

| Timeframe | Candles | Coverage | Interval | Purpose |
|-----------|---------|----------|----------|---------|
| 1m  | 500   | ~8h  | 60s  | Prediction trigger + context |
| 3m  | 4800  | ~10d | 180s | Context |
| 5m  | 2880  | ~10d | 300s | **Training main** |
| 10m | 1440  | ~10d | 600s | Context |
| 15m | 960   | ~10d | 900s | Context |
| 60m | 240   | ~10d | 3600s| Context |
| 1D  | 30    | ~30d | 3600s| Context |

### 2. Settings

```yaml
collector:
  candle_timeframe: 1
  max_candles_per_market: 500
  market_refresh_interval_min: 60
  train_timeframe: 5
  train_candles: 2880
  context_timeframes:
    - {minutes: 1, candles: 500, interval_sec: 60}
    - {minutes: 3, candles: 4800, interval_sec: 180}
    - {minutes: 10, candles: 1440, interval_sec: 600}
    - {minutes: 15, candles: 960, interval_sec: 900}
    - {minutes: 60, candles: 240, interval_sec: 3600}
  daily_candles: 30

strategy:
  lookahead_minutes: 30  # 5분봉 기준 shift=-6

data:
  stale_candle_days: 10
```

`CollectorConfig` changes:
- Remove: `train_timeframe: int`, `train_candles: int`, `daily_candles: int`
- Add: `train_timeframe: int = 5`, `train_candles: int = 2880`
- Add: `context_timeframes: tuple[ContextTimeframe, ...] = ()`
- Add: `daily_candles: int = 30`

New dataclass:
```python
@dataclass(frozen=True)
class ContextTimeframe:
    minutes: int
    candles: int
    interval_sec: int
```

### 3. Collector Changes

Replace `collect_train_candles()`:
- Collect train timeframe (5m) candles
- Collect all context timeframe candles
- Collect daily candles
- Group by interval for scheduling efficiency

### 4. FeatureBuilder Changes

Replace `build_daily_context()` and `_daily_feature_names()` with:

```python
def build_multi_context(self, context_dfs: dict[str, pd.DataFrame]) -> pd.Series:
    """Build context features from multiple timeframes.
    Keys: "1m", "3m", "10m", "15m", "60m", "1D"
    Each produces 6 features with prefix.
    """
```

Per-timeframe features (6 each, prefixed):
- `{tf}_rsi_14`, `{tf}_ema_5_ratio`, `{tf}_ema_20_ratio`
- `{tf}_volume_ratio`, `{tf}_trend`, `{tf}_atr_ratio`

Total: 24 (base) + 6×6 (context) = **60 features**

`get_feature_names()` returns 60 names.

Minimum rows required per timeframe for non-NaN context: 20.

### 5. Trainer Changes

- `daily_df` parameter → `context_dfs: dict[str, pd.DataFrame] | None`
- Calls `build_multi_context(context_dfs)` to get 36 context features
- `lookahead_minutes: 30` → `shift=-6` on 5-minute candles (6 × 5min = 30min)
- Everything else (scale_pos_weight, early stopping, F1) unchanged

### 6. Predictor Changes

- `daily_df` parameter → `context_dfs: dict[str, pd.DataFrame] | None`
- Calls `build_multi_context(context_dfs)` same as trainer
- Feature column alignment logic unchanged

### 7. App.py Changes

#### Scheduling
Group context collection by interval to avoid redundant schedules:
- 60s: already handled by `_collect_and_predict` (1m candles)
- 180s: 3m candles
- 300s: 5m candles (train data)
- 600s: 10m candles
- 900s: 15m candles
- 3600s: 60m + daily candles

Single `_collect_context_candles(interval_sec)` method collects all timeframes matching that interval.

#### Training/Prediction flow
Helper to build context_dfs dict:
```python
async def _build_context_dfs(self, market: str) -> dict[str, pd.DataFrame]:
    context_dfs = {}
    for ctx in self.settings.collector.context_timeframes:
        tf_str = f"{ctx.minutes}m"
        candles = await self.candle_repo.get_latest(market, tf_str, ctx.candles)
        if len(candles) >= 20:
            context_dfs[tf_str] = self._candles_to_df(candles)
    daily = await self.candle_repo.get_latest(market, "1D", self.settings.collector.daily_candles)
    if len(daily) >= 20:
        context_dfs["1D"] = self._candles_to_df(daily)
    return context_dfs
```

### 8. Other
- `stale_candle_days: 10`
- `strategy.lookahead_minutes: 30`
- Existing models auto-skipped (feature mismatch 24/30 vs 60)
- `deploy.sh --clean` deletes models

### 9. File Change Summary

| File | Change |
|------|--------|
| `config/settings.yaml` | context_timeframes list, train_timeframe=5, stale_candle_days=10, lookahead=30 |
| `src/config/settings.py` | ContextTimeframe dataclass, CollectorConfig fields |
| `src/service/collector.py` | Multi-timeframe collection |
| `src/service/features.py` | `build_multi_context()`, 60 feature names |
| `src/service/trainer.py` | `context_dfs` parameter |
| `src/service/predictor.py` | `context_dfs` parameter |
| `src/runtime/app.py` | Scheduling, `_build_context_dfs()`, training/prediction flow |
