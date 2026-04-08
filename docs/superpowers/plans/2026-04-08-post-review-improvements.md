# Post-Review Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코드 리뷰에서 발견된 4가지 보안/기능 개선 사항을 수정한다.

**Architecture:** auth.py 모듈의 JWT_SECRET 초기화 로직 변경, INVITE_CODE 검증 로직 반전, AuthConfig 연동 함수 추가, _ws_outbox를 user_id 키 dict로 전환.

**Tech Stack:** Python secrets 모듈, FastAPI, React (Register.tsx)

---

## File Structure

### 수정하는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/ui/api/auth.py` | JWT_SECRET 랜덤 생성, configure() 함수 추가 |
| `src/ui/api/routes/auth.py` | INVITE_CODE 로직 반전, /info 엔드포인트 추가 |
| `src/ui/api/server.py` | configure_auth 호출, WS outbox user_id 필터링 |
| `src/runtime/app.py` | _ws_outbox dict 전환, _push/_pop 헬퍼 |
| `src/ui/api/routes/exchange.py` | _push_ws_message 호출로 전환 |
| `src/ui/frontend/src/pages/Register.tsx` | invite_required 조건부 필드 |
| `tests/unit/test_auth.py` | JWT_SECRET 변경에 따른 테스트 수정 |

---

## Task 1: JWT_SECRET 랜덤 생성 + WARNING

**Files:**
- Modify: `src/ui/api/auth.py:1-15`
- Modify: `tests/unit/test_auth.py`

- [ ] **Step 1: auth.py의 JWT_SECRET 초기화 변경**

`src/ui/api/auth.py`의 상단을 수정:

```python
from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)

_env_secret = os.environ.get("JWT_SECRET", "")
if _env_secret:
    JWT_SECRET = _env_secret
else:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET not set — using random secret (tokens invalidate on restart)"
    )

INVITE_CODE = os.environ.get("INVITE_CODE", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

ACCESS_TOKEN_EXPIRE = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)
```

나머지 함수들(hash_password, verify_password, create_access_token 등)은 변경 없음.

- [ ] **Step 2: 테스트 실행**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: ALL PASS (테스트는 이미 `secret` 파라미터를 명시적으로 전달하므로 모듈 레벨 JWT_SECRET 변경에 영향 없음)

- [ ] **Step 3: 커밋**

```bash
git add src/ui/api/auth.py
git commit -m "security: use random JWT_SECRET when env var not set"
```

---

## Task 2: AuthConfig ↔ auth.py 연동

**Files:**
- Modify: `src/ui/api/auth.py`
- Modify: `src/ui/api/server.py:16-17`

- [ ] **Step 1: auth.py에 configure 함수 추가**

`src/ui/api/auth.py`의 `REFRESH_TOKEN_EXPIRE = ...` 뒤에 추가:

```python
def configure_auth(access_expire_minutes: int, refresh_expire_days: int) -> None:
    """Update token expiration from settings. Called once at startup."""
    global ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE
    ACCESS_TOKEN_EXPIRE = timedelta(minutes=access_expire_minutes)
    REFRESH_TOKEN_EXPIRE = timedelta(days=refresh_expire_days)
```

- [ ] **Step 2: server.py에서 configure_auth 호출**

`src/ui/api/server.py`에서 import 추가:

```python
from src.ui.api.auth import configure_auth, decode_token
```

`create_app()` 함수 내부, `@app.get("/api/health")` 정의 전에 startup 이벤트 추가:

```python
@app.on_event("startup")
async def _configure_auth_on_startup() -> None:
    app_instance = getattr(app.state, "app", None)
    if app_instance:
        cfg = app_instance.settings.auth
        configure_auth(cfg.access_token_expire_minutes, cfg.refresh_token_expire_days)
```

- [ ] **Step 3: 테스트 실행**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 4: 커밋**

```bash
git add src/ui/api/auth.py src/ui/api/server.py
git commit -m "feat: wire AuthConfig to auth module via configure_auth()"
```

---

## Task 3: INVITE_CODE 오픈 가입 + /info 엔드포인트

**Files:**
- Modify: `src/ui/api/routes/auth.py:18-37`
- Modify: `src/ui/frontend/src/pages/Register.tsx`

- [ ] **Step 1: RegisterRequest에서 invite_code를 optional로 변경**

`src/ui/api/routes/auth.py`의 `RegisterRequest` 수정:

```python
class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str
    invite_code: str = ""
```

- [ ] **Step 2: register 엔드포인트의 검증 로직 반전**

`src/ui/api/routes/auth.py`의 register 함수 (라인 36):

```python
# 현재:
#   if not INVITE_CODE or body.invite_code != INVITE_CODE:
# 변경:
    if INVITE_CODE and body.invite_code != INVITE_CODE:
        raise HTTPException(status_code=400, detail="Invalid invite code")
```

- [ ] **Step 3: /info 엔드포인트 추가**

`src/ui/api/routes/auth.py`의 `router` 정의 직후 (라인 15-16 부근)에 추가:

```python
@router.get("/info")
async def auth_info():
    return {"invite_required": bool(INVITE_CODE)}
```

- [ ] **Step 4: Register.tsx에서 invite_required 조건부 처리**

`src/ui/frontend/src/pages/Register.tsx` 전체 교체:

```tsx
import { useState, useEffect, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_URL || "";

interface Props {
  onRegister: (
    email: string, password: string, nickname: string, inviteCode: string,
  ) => Promise<any>;
}

export default function Register({ onRegister }: Props) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [inviteRequired, setInviteRequired] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/auth/info`)
      .then(r => r.json())
      .then(data => setInviteRequired(data.invite_required))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다");
      return;
    }
    setLoading(true);
    try {
      await onRegister(email, password, nickname, inviteCode);
      navigate("/login");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">Paper Trader</h1>
        <p className="auth-subtitle">회원가입</p>
        <form onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="form-group">
            <label>이메일</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus />
          </div>
          <div className="form-group">
            <label>닉네임</label>
            <input type="text" value={nickname} onChange={e => setNickname(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>비밀번호</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
          </div>
          {inviteRequired && (
            <div className="form-group">
              <label>초대 코드</label>
              <input type="text" value={inviteCode} onChange={e => setInviteCode(e.target.value)} required />
            </div>
          )}
          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "가입 중..." : "가입하기"}
          </button>
        </form>
        <p className="auth-link">
          이미 계정이 있으신가요? <Link to="/login">로그인</Link>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add src/ui/api/routes/auth.py src/ui/frontend/src/pages/Register.tsx
git commit -m "feat: allow open registration when INVITE_CODE not set"
```

---

## Task 4: _ws_outbox 사용자별 분리

**Files:**
- Modify: `src/runtime/app.py:103,677,695`
- Modify: `src/ui/api/server.py:90-92`
- Modify: `src/ui/api/routes/exchange.py:104,174`

- [ ] **Step 1: app.py — _ws_outbox 타입 변경 + 헬퍼 추가**

`src/runtime/app.py` 라인 103 수정:

```python
# 현재:
#   self._ws_outbox: list[dict[str, object]] = []
# 변경:
        self._ws_outbox: dict[int, list[dict[str, object]]] = {}
```

`__init__` 메서드 뒤, `_candles_to_df` 메서드 전에 헬퍼 추가:

```python
    def _push_ws_message(self, user_id: int, msg: dict[str, object]) -> None:
        self._ws_outbox.setdefault(user_id, []).append(msg)

    def _pop_ws_messages(self, user_id: int) -> list[dict[str, object]]:
        return self._ws_outbox.pop(user_id, [])
```

- [ ] **Step 2: app.py — _monitor_user_positions 호출부 변경**

`src/runtime/app.py`의 `_monitor_user_positions` 메서드 내에서 2곳 변경:

라인 677 부근 (전체 매도 exits 루프):
```python
# 현재:
#   self._ws_outbox.append({...})
# 변경:
            self._push_ws_message(user_id, {
                "type": "order_filled",
                "data": {
                    "market": order.market, "side": order.side.value,
                    "reason": order.reason, "price": str(order.fill_price),
                },
            })
```

라인 695 부근 (부분 매도 partial_exits 루프):
```python
# 현재:
#   self._ws_outbox.append({...})
# 변경:
            self._push_ws_message(user_id, {
                "type": "order_filled",
                "data": {
                    "market": order.market, "side": order.side.value,
                    "reason": order.reason, "price": str(order.fill_price),
                },
            })
```

- [ ] **Step 3: exchange.py — _push_ws_message 호출로 변경**

`src/ui/api/routes/exchange.py` 라인 104 부근 (buy):
```python
# 현재:
#   app._ws_outbox.append({...})
# 변경:
    app._push_ws_message(user_id, {
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })
```

라인 174 부근 (sell):
```python
# 현재:
#   app._ws_outbox.append({...})
# 변경:
    app._push_ws_message(user_id, {
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })
```

- [ ] **Step 4: server.py — WebSocket에서 user_id 기반 outbox 폴링**

`src/ui/api/server.py` 라인 90-92 변경:

```python
                # 현재:
                # if app_instance and hasattr(app_instance, "_ws_outbox"):
                #     while app_instance._ws_outbox:
                #         messages.append(app_instance._ws_outbox.pop(0))

                # 변경:
                if app_instance and hasattr(app_instance, "_ws_outbox"):
                    for msg in app_instance._pop_ws_messages(user_id):
                        messages.append(msg)
```

- [ ] **Step 5: 구조 테스트 실행**

Run: `uv run pytest tests/structural/ -v`
Expected: ALL PASS

- [ ] **Step 6: 커밋**

```bash
git add src/runtime/app.py src/ui/api/server.py src/ui/api/routes/exchange.py
git commit -m "fix: isolate WebSocket outbox per user to prevent cross-user notification leaks"
```

---

## 실행 순서 요약

| Task | 내용 | 의존성 |
|------|------|--------|
| 1 | JWT_SECRET 랜덤 생성 | 없음 |
| 2 | AuthConfig 연동 | Task 1 (auth.py 수정 후) |
| 3 | INVITE_CODE 오픈 가입 | 없음 |
| 4 | _ws_outbox 유저별 분리 | 없음 |

Task 1→2는 순차, Task 3과 4는 독립적.
