# Post-Review Improvements Design

코드 리뷰에서 발견된 4가지 개선 사항을 해결하는 설계.

## 1. INVITE_CODE 미설정 시 오픈 가입

### 문제

`INVITE_CODE` 환경변수가 비어있으면 `not INVITE_CODE`가 True가 되어 모든 가입 요청이 거부됨.

### 변경

**`src/ui/api/routes/auth.py` — register 엔드포인트:**

```python
# 현재 (항상 거부)
if not INVITE_CODE or body.invite_code != INVITE_CODE:
    raise HTTPException(...)

# 변경 (미설정 시 스킵)
if INVITE_CODE and body.invite_code != INVITE_CODE:
    raise HTTPException(...)
```

**`src/ui/api/routes/auth.py` — 신규 엔드포인트:**

```python
@router.get("/info")
async def auth_info():
    return {"invite_required": bool(INVITE_CODE)}
```

프론트엔드에서 가입 페이지 렌더링 전에 이 엔드포인트를 호출하여 초대 코드 필드 표시 여부를 결정.

**`src/ui/frontend/src/pages/Register.tsx`:**

- 컴포넌트 마운트 시 `GET /api/auth/info` 호출
- `invite_required == false`이면 초대 코드 입력 필드 숨김, 빈 문자열로 전송

## 2. JWT_SECRET 미설정 시 랜덤 생성 + WARNING

### 문제

`JWT_SECRET` 기본값이 `"change-me-in-production"`으로 하드코딩되어 있어 소스 코드를 아는 사람이 토큰을 위조할 수 있음.

### 변경

**`src/ui/api/auth.py`:**

```python
import secrets

_env_secret = os.environ.get("JWT_SECRET", "")
if _env_secret:
    JWT_SECRET = _env_secret
else:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET not set — using random secret (tokens invalidate on restart)"
    )
```

- 모듈 임포트 시 1회 실행, 프로세스 수명 동안 고정
- 개발 환경: 설정 없이 동작, 재시작 시 토큰 무효화 (보안 이점)
- 프로덕션: `.env`에 고정값 설정

## 3. AuthConfig ↔ auth.py 연동

### 문제

`settings.py`의 `AuthConfig(access_token_expire_minutes, refresh_token_expire_days)`와 `auth.py`의 모듈 레벨 상수 `ACCESS_TOKEN_EXPIRE`, `REFRESH_TOKEN_EXPIRE`가 분리되어 있음. YAML 설정을 변경해도 실제 만료 시간에 반영되지 않음.

### 변경

**`src/ui/api/auth.py` — configure 함수 추가:**

```python
def configure(auth_config: AuthConfig) -> None:
    global ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE
    ACCESS_TOKEN_EXPIRE = timedelta(minutes=auth_config.access_token_expire_minutes)
    REFRESH_TOKEN_EXPIRE = timedelta(days=auth_config.refresh_token_expire_days)
```

**`src/ui/api/server.py` — create_app()에서 호출:**

```python
from src.ui.api.auth import configure as configure_auth

# lifespan 또는 startup에서:
configure_auth(app.state.app.settings.auth)
```

- 기존 `create_access_token(user_id)` 등의 호출 시그니처 변경 없음
- 기본값은 현재와 동일 (30분 / 7일), YAML로 오버라이드 가능

## 4. _ws_outbox 사용자별 분리

### 문제

`app._ws_outbox`가 단일 `list[dict]`라서 유저 A의 매매 알림이 유저 B의 WebSocket으로도 전달됨.

### 변경

**`src/runtime/app.py`:**

```python
# 타입 변경
self._ws_outbox: dict[int, list[dict]] = {}

# 헬퍼 메서드 추가
def _push_ws_message(self, user_id: int, msg: dict) -> None:
    self._ws_outbox.setdefault(user_id, []).append(msg)

def _pop_ws_messages(self, user_id: int) -> list[dict]:
    return self._ws_outbox.pop(user_id, [])
```

**호출부 변경:**

| 파일 | 현재 | 변경 |
|------|------|------|
| `app.py` `_monitor_user_positions` | `self._ws_outbox.append({...})` | `self._push_ws_message(user_id, {...})` |
| `exchange.py` buy/sell | `app._ws_outbox.append({...})` | `app._push_ws_message(user["id"], {...})` |

**`src/ui/api/server.py` — WebSocket 핸들러:**

```python
# 현재: trading_app._ws_outbox 전체 폴링
# 변경: 인증된 user_id의 메시지만 폴링
queued = trading_app._pop_ws_messages(user_id)
for msg in queued:
    await websocket.send_json(msg)
```

WebSocket 핸들러는 이미 토큰에서 `user_id`를 추출하므로 추가 인증 로직 불필요.

## 변경 범위 요약

| 파일 | 개선 항목 |
|------|----------|
| `src/ui/api/auth.py` | #2 JWT_SECRET, #3 configure() |
| `src/ui/api/routes/auth.py` | #1 INVITE_CODE, /info 엔드포인트 |
| `src/ui/api/server.py` | #3 configure 호출, #4 WS user_id 필터링 |
| `src/runtime/app.py` | #4 _ws_outbox dict화 + 헬퍼 |
| `src/ui/api/routes/exchange.py` | #4 _push_ws_message 호출 |
| `src/ui/frontend/src/pages/Register.tsx` | #1 invite_required 조건부 필드 |
