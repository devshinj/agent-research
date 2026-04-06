# Hot Reload Settings Design

## Problem

현재 설정 변경은 `POST /api/control/reset`으로만 가능하며, 잔고·포지션·거래내역이 모두 초기화된다. 모의매매 중 리스크 파라미터나 스크리닝 기준을 조정해보고 싶을 때 매번 완전 초기화해야 하는 불편함이 있다.

## Goals

1. **핫 리로드**: 매매 시스템 중단 없이 허용된 설정 항목을 런타임에 변경
2. **완전 초기화**: 기존 reset 유지 — 전체 설정 교체 + 잔고/포지션/거래내역 리셋

## Hot-Reload Field Classification

### 핫 리로드 가능 (매매 중단 없이 변경)

| 섹션 | 필드 | 근거 |
|------|------|------|
| risk | stop_loss_pct, take_profit_pct, trailing_stop_pct | 다음 틱부터 새 기준 적용 |
| risk | max_daily_trades, consecutive_loss_limit, cooldown_minutes | 런타임 카운터 보존, 한도만 변경 |
| strategy | min_confidence | 다음 예측부터 새 임계값 적용 |
| screening | min_volume_krw, min_volatility_pct, max_volatility_pct | 다음 스크리닝 주기에 반영 |
| screening | max_coins, always_include | 다음 스크리닝 주기에 반영 |

### 완전 초기화에서만 변경

| 섹션 | 필드 | 근거 |
|------|------|------|
| paper_trading | initial_balance, max_position_pct, max_open_positions | 열린 포지션의 손익 계산 일관성 |
| paper_trading | fee_rate, slippage_rate, min_order_krw | 주문 실행 로직에 직접 영향 |
| strategy | lookahead_minutes, threshold_pct, retrain_interval_hours | 모델 학습 파라미터, 스케줄러 간격 |
| collector | candle_timeframe, max_candles_per_market, market_refresh_interval_min | 인프라 수준 설정 |
| data | db_path, model_dir, stale_candle_days, stale_model_days, stale_order_days | 인프라 수준 설정 |

### 기존 포지션 처리 정책

핫 리로드 시 기존 포지션은 그대로 유지한다. 새 설정은 "다음 매매부터" 적용된다.

## API Design

### `PATCH /api/control/config` (신규)

핫 리로드 엔드포인트. 허용된 필드만 부분 업데이트한다.

**Request:**
```json
{
  "risk": { "stop_loss_pct": 0.03 },
  "screening": { "max_coins": 10 }
}
```

**Success Response (200):**
```json
{
  "status": "updated",
  "updated_fields": { "risk": ["stop_loss_pct"], "screening": ["max_coins"] },
  "config": { ... }  // 전체 설정 반환
}
```

**Error Response (400):**
```json
{
  "detail": "핫 리로드 불가 필드: paper_trading.fee_rate — 완전 초기화를 사용하세요"
}
```

### `POST /api/control/reset` (기존 유지)

전체 설정 교체 + 완전 초기화. 변경 없음.

## Backend Changes

### 1. `App.HOT_RELOAD_FIELDS` — 화이트리스트

```python
HOT_RELOAD_FIELDS: dict[str, set[str]] = {
    "risk": {
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
        "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
    },
    "strategy": {"min_confidence"},
    "screening": {
        "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
        "max_coins", "always_include",
    },
}
```

### 2. `App.hot_reload(patches)` 메서드

1. `patches` dict에서 허용되지 않은 필드가 있으면 ValueError 발생
2. frozen dataclass이므로 `dataclasses.replace()`로 새 config 객체 생성
3. 영향받는 서비스의 update 메서드 호출
4. `self.settings`를 새 Settings 객체로 교체
5. YAML 파일에 저장
6. 변경된 필드 목록 반환

### 3. 서비스 update 메서드 (신규)

각 서비스에 config 참조만 교체하는 경량 메서드 추가:

- `RiskManager.update_config(risk: RiskConfig, pt: PaperTradingConfig)` — `self._risk`, `self._pt` 교체. `_consecutive_losses`, `_cooldown_until`, `_daily_trades` 등 런타임 상태는 보존.
- `Predictor.update_min_confidence(value: float)` — `self._min_confidence` 교체. `_models` dict 보존.
- `Screener.update_config(config: ScreeningConfig)` — `self._config` 교체.

### 4. `PATCH /api/control/config` 라우트

`src/ui/api/routes/control.py`에 추가:

1. request body 파싱
2. `app.hot_reload(body)` 호출
3. 성공 시 200 + 변경 필드 + 전체 config 반환
4. ValueError 시 400 반환

## Frontend Changes

### Settings 페이지 수정

기존 "초기화 & 재설정" 버튼 옆에 **"설정 변경"** 버튼 추가:

- **"설정 변경"** 클릭 → 핫 리로드 가능 필드만 편집 모드로 전환 (나머지는 읽기 전용)
  - 매매 엔진 중단 없음 (pause 호출 안 함)
  - "적용" 버튼 → `PATCH /api/control/config`로 변경분만 전송
  - 확인 모달 없음 (파괴적 동작이 아니므로)
- **"초기화 & 재설정"** 클릭 → 기존 동작 유지 (pause → 전체 편집 → 확인 모달 → reset → resume)

### 편집 모드 구분

- 핫 리로드 모드: 허용 필드만 input, 나머지는 회색 텍스트로 표시
- 초기화 모드: 전체 필드 input (기존과 동일)

## Testing

### 단위 테스트

1. `App.hot_reload()` — 허용 필드 변경 시 서비스 config 갱신 확인
2. `App.hot_reload()` — 금지 필드 포함 시 ValueError 발생 확인
3. `RiskManager.update_config()` — config 교체 후 런타임 상태 보존 확인
4. `Predictor.update_min_confidence()` — 모델 dict 보존 확인
5. `Screener.update_config()` — config 교체 확인

### API 테스트

6. `PATCH /api/control/config` — 허용 필드만 전송 시 200 + 설정 반영
7. `PATCH /api/control/config` — 금지 필드 포함 시 400 에러
8. `PATCH /api/control/config` → `GET /api/control/config` — 변경 사항이 유지되는지 확인

## Files to Modify

| 파일 | 변경 |
|------|------|
| `src/runtime/app.py` | `HOT_RELOAD_FIELDS` 상수, `hot_reload()` 메서드 추가 |
| `src/service/risk_manager.py` | `update_config()` 메서드 추가 |
| `src/service/predictor.py` | `update_min_confidence()` 메서드 추가 |
| `src/service/screener.py` | `update_config()` 메서드 추가 |
| `src/ui/api/routes/control.py` | `PATCH /config` 라우트 추가 |
| `src/ui/frontend/src/pages/Settings.tsx` | 핫 리로드 모드 UI 추가 |
| `tests/unit/test_hot_reload.py` | 단위 + API 테스트 |
