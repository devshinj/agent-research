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
