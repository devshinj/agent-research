# Risk Slider UI Design

## Overview

Risk.tsx 페이지의 하드코딩된 "리스크 규칙" 섹션을 인터랙티브 슬라이더 폼으로 교체하여, 사용자가 매매 빈도와 거래량에 영향을 주는 파라미터를 실시간으로 조절할 수 있게 한다.

## Scope

### In scope

- Risk.tsx "리스크 규칙" 패널을 슬라이더 UI로 교체
- `paper_trading` 섹션의 `max_position_pct`, `max_open_positions` 2개 필드를 hot-reload에 추가
- `hot_reload()` 메서드에 `paper_trading` 패치 처리 블록 추가
- 리스크 메트릭 카드의 하드코딩 한도값을 서버 설정값으로 연동 (기존 불일치 수정)

### Out of scope

- `stop_loss_pct`, `take_profit_pct`, `trailing_stop_pct` (매매 빈도/거래량과 직접 무관, Settings 페이지에서 이미 조절 가능)
- 프리셋 기능 (보수적/공격적 등)
- WebSocket 실시간 동기화

## Backend Changes

### 1. `App.HOT_RELOAD_FIELDS` 확장 (`src/runtime/app.py`)

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
    "paper_trading": {"max_position_pct", "max_open_positions"},  # NEW
}
```

### 2. `hot_reload()` 메서드에 `paper_trading` 처리 추가

`paper_trading` 섹션이 패치에 포함되면:
- `PaperTradingConfig`를 `dataclasses.replace`로 갱신
- `self.settings`에 반영
- `self.risk_manager._pt` 업데이트
- `self.paper_engine._config` 업데이트 (PaperEngine에 `update_config` 메서드 추가)

필드별 타입 변환:
- `max_position_pct` → `Decimal`
- `max_open_positions` → `int`

## Frontend Changes

### 1. Risk.tsx "리스크 규칙" 패널 → "투자 성향 조절" 패널

기존 하드코딩된 규칙 목록을 제거하고 슬라이더 폼으로 교체.

### 2. 슬라이더 사양

| 파라미터 | 라벨 | 범위 | step | 단위 | config 섹션 |
|---------|------|------|------|------|-------------|
| `max_daily_trades` | 일일 최대 거래 | 10–500 | 10 | 회 | `risk` |
| `consecutive_loss_limit` | 연속 손실 한도 | 3–20 | 1 | 회 | `risk` |
| `cooldown_minutes` | 쿨다운 시간 | 5–120 | 5 | 분 | `risk` |
| `max_position_pct` | 포지션 최대 비중 | 0.1–1.0 | 0.05 | % 표시 (×100) | `paper_trading` |
| `max_open_positions` | 동시 포지션 수 | 1–10 | 1 | 개 | `paper_trading` |

### 3. 동작 흐름

1. **페이지 로드**: `GET /api/control/config` → 슬라이더 초기값 설정
2. **슬라이더 조절**: 로컬 state만 변경, 서버 미반영
3. **"적용" 버튼 클릭**: 변경된 필드만 `PATCH /api/control/config`로 전송
4. **성공**: 배지/상태 표시로 "적용 완료" 피드백
5. **실패**: 에러 메시지 표시
6. **"초기화" 버튼**: 로컬 state를 서버에서 가져온 원래 값으로 되돌림

### 4. UI 구조

```
┌─────────────────────────────────────────┐
│ 투자 성향 조절                           │
├─────────────────────────────────────────┤
│                                         │
│  일일 최대 거래        ──●────── 200회   │
│  연속 손실 한도        ────●──── 10회    │
│  쿨다운 시간           ──●────── 60분   │
│  포지션 최대 비중      ──────●── 80%    │
│  동시 포지션 수        ────●──── 6개    │
│                                         │
│              [ 초기화 ]  [ 적용 ]        │
└─────────────────────────────────────────┘
```

### 5. 메트릭 카드 하드코딩 수정

현재 Risk.tsx의 메트릭 카드 3개에 한도값이 하드코딩되어 실제 설정과 불일치한다. `GET /api/control/config`로 가져온 설정값으로 교체:

| 카드 | 현재 하드코딩 | 실제 설정 | 연동 필드 |
|------|-------------|----------|----------|
| 일일 손실 바 | 5% 한도 | 10% | `risk.max_daily_loss_pct` |
| 연속 손실 | `/ 5` | 10 | `risk.consecutive_loss_limit` |
| 일일 거래 횟수 | `/ 50` | 200 | `risk.max_daily_trades` |

슬라이더로 `consecutive_loss_limit`, `max_daily_trades`를 변경하면 메트릭 카드의 한도 표시도 자동으로 갱신된다.

### 6. 변경하지 않는 기존 요소

- 서킷 브레이커 상태 패널 (상단)
- 리스크 메트릭 카드 3개의 레이아웃/디자인 (한도값만 동적으로 변경)

## API Contract

### Request

```
PATCH /api/control/config
Content-Type: application/json

{
  "risk": {
    "max_daily_trades": 300,
    "consecutive_loss_limit": 15
  },
  "paper_trading": {
    "max_position_pct": 0.9
  }
}
```

### Response

```json
{
  "status": "updated",
  "updated_fields": {
    "risk": ["max_daily_trades", "consecutive_loss_limit"],
    "paper_trading": ["max_position_pct"]
  },
  "config": { ... }
}
```

## Testing

- `hot_reload()`에 `paper_trading` 섹션 패치 시 `PaperTradingConfig` 갱신 확인
- 허용 범위 밖 필드 패치 시 `ValueError` 발생 확인
- 프론트엔드: 슬라이더 조절 → 적용 → 서버 값 반영 확인
