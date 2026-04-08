# ML 2-Class 전환 + Strategy Hot Reload 설계

## 배경

500개 캔들 기반 3-class(BUY/HOLD/SELL) LightGBM 모델이 신뢰도 0.45 임계값을 넘지 못해
활성 신호가 한 번도 발생하지 않음. 근본 원인:

1. 3-class에서 랜덤 확률 0.33 → 과소적합 모델의 max probability가 0.35~0.40 수준
2. 90:5:5 라벨 불균형 (HOLD 압도적)
3. SELL 라벨은 실질적으로 사용되지 않음 (risk manager가 매도 담당)

## 변경 사항

### 1. 2-Class 전환 (BUY vs NOT_BUY)

**Trainer (`_create_labels`)**
- 기존: `{0: SELL, 1: HOLD, 2: BUY}` 3-class
- 변경: `{0: NOT_BUY, 1: BUY}` binary classification
- `future_return > threshold` → BUY(1), 나머지 전부 → NOT_BUY(0)

**Predictor**
- `LABEL_TO_SIGNAL`: `{0: HOLD, 1: BUY}`
- `_compute_basis`: n_classes 자동 감소 (reshape 로직 그대로 동작)
- 2-class `predict_proba`에서 BUY 확률이 0.5를 넘기가 훨씬 용이

**유지 사항**
- `SignalType.SELL` enum 값 유지 (risk manager 매도 로직에서 사용)
- 프론트엔드 SELL 표시 코드 유지 (신호 분포 바에서 0으로 표시될 뿐)
- 매도 자동화: stop-loss, take-profit, trailing stop → 기존대로 risk manager 담당

### 2. `threshold_pct` Hot Reload

**현재 상태**
- `min_confidence`: hot reload 지원 (이미 구현됨)
- `threshold_pct`: Trainer 생성자에서 고정, hot reload 불가

**변경**
- `Trainer.update_threshold(value)` 메서드 추가
- `HOT_RELOAD_FIELDS["strategy"]`에 `"threshold_pct"` 추가
- `hot_reload()`에서 threshold 변경 감지 시:
  1. `trainer._threshold` 업데이트
  2. `asyncio.create_task(_retrain())` 비동기 재학습 트리거
- 기존 모델은 이전 threshold 기준 라벨이므로 재학습 필수

### 3. 프론트엔드

- `Strategy.tsx`의 `threshold_pct` 필드: `hotReload: false → true`
- desc 업데이트: BUY/SELL → BUY 기준 설명으로 변경

## 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/service/trainer.py` | `_create_labels` 2-class, `update_threshold()` 추가 |
| `src/service/predictor.py` | `LABEL_TO_SIGNAL` 2-class 매핑 |
| `src/runtime/app.py` | HOT_RELOAD_FIELDS에 threshold_pct 추가, hot_reload()에 재학습 트리거 |
| `src/ui/frontend/src/pages/Strategy.tsx` | threshold_pct hotReload: true, desc 변경 |
| 테스트 파일들 | 2-class에 맞게 라벨/예측값 수정 |
