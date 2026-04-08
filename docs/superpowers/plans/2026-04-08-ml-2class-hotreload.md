# ML 2-Class 전환 + threshold_pct Hot Reload 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 3-class ML 분류를 2-class(BUY vs NOT_BUY)로 전환하고, threshold_pct를 런타임 hot reload 가능하게 하여 관리자가 ML 전략 파라미터를 즉시 조절할 수 있게 한다.

**Architecture:** Trainer의 라벨링을 binary로 변경하고, Predictor의 매핑을 2-class에 맞게 수정한다. threshold_pct를 HOT_RELOAD_FIELDS에 추가하고 변경 시 자동 재학습을 트리거한다. 프론트엔드 슬라이더를 활성화한다.

**Tech Stack:** Python 3.12, LightGBM, FastAPI, React/TypeScript

---

## File Structure

| 파일 | 역할 | 변경 |
|------|------|------|
| `src/service/trainer.py` | ML 모델 학습 | `_create_labels` 2-class, `update_threshold()` 추가 |
| `src/service/predictor.py` | ML 예측 | `LABEL_TO_SIGNAL` 2-class 매핑 |
| `src/runtime/app.py` | 앱 런타임 | HOT_RELOAD_FIELDS, hot_reload() 수정 |
| `src/ui/frontend/src/pages/Strategy.tsx` | 전략 설정 UI | threshold_pct hotReload 활성화 |
| `tests/unit/test_trainer.py` | Trainer 단위 테스트 | 2-class 라벨 검증 추가 |
| `tests/unit/test_predictor.py` | Predictor 단위 테스트 | SELL 제거 반영 |
| `tests/unit/test_hot_reload.py` | Hot reload 단위 테스트 | threshold_pct 테스트 추가 |
| `tests/integration/test_training_integration.py` | 통합 테스트 | 2-class 반영 |

---

### Task 1: Trainer 2-class 전환 + update_threshold

**Files:**
- Modify: `src/service/trainer.py:32-39`
- Test: `tests/unit/test_trainer.py`

- [ ] **Step 1: Write failing test for 2-class labels**

`tests/unit/test_trainer.py`에 추가:

```python
def test_trainer_creates_binary_labels(tmp_path):
    """_create_labels produces only 0 (NOT_BUY) and 1 (BUY), no label=2."""
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    labels = trainer._create_labels(df)
    assert set(labels.dropna().unique()).issubset({0, 1})


def test_trainer_update_threshold(tmp_path):
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    trainer.update_threshold(0.5)
    assert trainer._threshold == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trainer.py::test_trainer_creates_binary_labels tests/unit/test_trainer.py::test_trainer_update_threshold -v`
Expected: `test_trainer_creates_binary_labels` FAIL (label 2 exists), `test_trainer_update_threshold` FAIL (no method)

- [ ] **Step 3: Implement 2-class labels and update_threshold**

`src/service/trainer.py` — `_create_labels` 메서드를 다음으로 교체:

```python
def _create_labels(self, df: pd.DataFrame) -> pd.Series:
    future_return = (
        df["close"].shift(-self._lookahead) / df["close"] - 1
    ) * 100
    labels = pd.Series(0, index=df.index)  # default NOT_BUY=0
    labels[future_return > self._threshold] = 1  # BUY
    return labels
```

같은 파일에 `update_threshold` 메서드 추가 (`__init__` 아래):

```python
def update_threshold(self, value: float) -> None:
    self._threshold = value
```

- [ ] **Step 4: Run all trainer tests**

Run: `uv run pytest tests/unit/test_trainer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/trainer.py tests/unit/test_trainer.py
git commit -m "feat: convert Trainer to 2-class (BUY vs NOT_BUY) + add update_threshold"
```

---

### Task 2: Predictor 2-class 매핑

**Files:**
- Modify: `src/service/predictor.py:19`
- Test: `tests/unit/test_predictor.py`

- [ ] **Step 1: Update test assertions for 2-class**

`tests/unit/test_predictor.py` — `test_predictor_returns_signal_and_basis` 함수에서 라인 40의 assertion을 변경:

```python
assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
```

`tests/integration/test_training_integration.py` — 두 테스트 함수에서 `SignalType.SELL` 포함된 assertion을 변경:

라인 40:
```python
assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
```

라인 56:
```python
assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_predictor.py::test_predictor_returns_signal_and_basis tests/integration/test_training_integration.py -v`
Expected: FAIL — 모델이 아직 3-class라서 SELL이 나올 수 있음 (또는 LABEL_TO_SIGNAL 매핑 오류)

- [ ] **Step 3: Update LABEL_TO_SIGNAL**

`src/service/predictor.py` — 라인 19를 변경:

```python
LABEL_TO_SIGNAL = {0: SignalType.HOLD, 1: SignalType.BUY}
```

- [ ] **Step 4: Run all predictor and integration tests**

Run: `uv run pytest tests/unit/test_predictor.py tests/integration/test_training_integration.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/predictor.py tests/unit/test_predictor.py tests/integration/test_training_integration.py
git commit -m "feat: update Predictor to 2-class signal mapping (HOLD/BUY)"
```

---

### Task 3: threshold_pct hot reload + 자동 재학습 트리거

**Files:**
- Modify: `src/runtime/app.py:44-59` (HOT_RELOAD_FIELDS), `src/runtime/app.py:442-443` (hot_reload strategy block)
- Test: `tests/unit/test_hot_reload.py`

- [ ] **Step 1: Write failing test for threshold_pct hot reload**

`tests/unit/test_hot_reload.py`에 추가:

```python
def test_hot_reload_updates_threshold_pct():
    """hot_reload with strategy.threshold_pct updates trainer threshold."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    app.hot_reload({"strategy": {"threshold_pct": 0.5}})

    assert app.trainer._threshold == 0.5
    assert app.settings.strategy.threshold_pct == Decimal("0.5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_hot_reload.py::test_hot_reload_updates_threshold_pct -v`
Expected: FAIL with "핫 리로드 불가 필드: strategy.threshold_pct"

- [ ] **Step 3: Implement hot reload for threshold_pct**

`src/runtime/app.py` — `HOT_RELOAD_FIELDS`의 `"strategy"` set에 `"threshold_pct"` 추가:

```python
"strategy": {"min_confidence", "threshold_pct"},
```

`src/runtime/app.py` — `hot_reload()` 메서드의 `if "strategy" in patches:` 블록 (라인 442-443 부근)을 변경:

```python
if "strategy" in patches:
    self.predictor.update_min_confidence(float(new_strategy.min_confidence))
    if "threshold_pct" in patches["strategy"]:
        self.trainer.update_threshold(float(new_strategy.threshold_pct))
        import asyncio
        asyncio.create_task(self._retrain())
```

- [ ] **Step 4: Run all hot reload tests**

Run: `uv run pytest tests/unit/test_hot_reload.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/app.py tests/unit/test_hot_reload.py
git commit -m "feat: add threshold_pct hot reload with auto-retrain trigger"
```

---

### Task 4: 프론트엔드 threshold_pct 슬라이더 활성화

**Files:**
- Modify: `src/ui/frontend/src/pages/Strategy.tsx:96`

- [ ] **Step 1: Update STRATEGY_FIELDS entry**

`src/ui/frontend/src/pages/Strategy.tsx` — 라인 96의 `threshold_pct` 필드 정의를 변경:

```typescript
{ section: "strategy", key: "threshold_pct", label: "분류 임계값", desc: "이 비율 이상 상승이 예상되면 BUY로 분류합니다 (변경 시 자동 재학습)", min: 0.1, max: 1.0, step: 0.05, format: (v) => `${v}%`, hotReload: true },
```

- [ ] **Step 2: Verify build succeeds**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Strategy.tsx
git commit -m "feat: enable threshold_pct hot reload slider in Strategy UI"
```

---

### Task 5: 전체 테스트 실행 + 기존 모델 삭제

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Delete stale 3-class models (if data/models exists)**

```bash
rm -rf data/models/*/
```

기존 3-class 모델은 2-class와 호환 불가하므로 삭제. 다음 retrain 주기에 자동으로 2-class 모델이 생성됨.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: clean up stale 3-class models"
```
