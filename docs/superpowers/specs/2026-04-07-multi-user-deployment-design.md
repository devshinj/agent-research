# Multi-User Deployment Design

## Overview

기존 단일 사용자 로컬 앱을 개인 리눅스 서버에 배포하여, 소수 지인이 각자 독립된 매매 설정과 포트폴리오로 페이퍼 트레이딩을 사용할 수 있게 한다.

## 핵심 결정사항

| 항목 | 결정 |
|------|------|
| 사용자 범위 | 소수 지인 (각자 독립 포트폴리오) |
| 서버 | 개인 리눅스 서버 (192.168.102.150) |
| 매매 | 페이퍼 트레이딩만 |
| 독립성 | 시장 데이터/ML 공유, 매매 설정+포트폴리오만 사용자별 분리 |
| 가입 | 이메일 + 비밀번호 + 마스터 초대코드 |
| 관리자 | 1명 (첫 번째 가입자 또는 환경변수로 지정) |
| 배포 | Docker Compose (멀티스테이지 빌드 + docker save/load) |
| HTTPS | Nginx + 자체 서명 인증서 (IP 접속) |
| DB | SQLite 유지 (기존 테이블에 user_id 추가) |

---

## 1. 인증 시스템

### DB 스키마

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
```

### 인증 흐름

- **가입**: `POST /api/auth/register` — 이메일 + 비밀번호 + 닉네임 + 초대코드
  - 초대코드는 환경변수 `INVITE_CODE`로 설정
  - 비밀번호는 bcrypt로 해싱, 최소 8자
  - 첫 번째 가입자를 자동 관리자로 지정 (또는 `ADMIN_EMAIL` 환경변수)

- **로그인**: `POST /api/auth/login` — 이메일 + 비밀번호 → JWT access token + refresh token
  - access token: 30분 만료
  - refresh token: 7일 만료, `POST /api/auth/refresh`로 갱신

- **인증 미들웨어**: FastAPI `Depends`로 전 API에 적용
  - `/api/auth/*`, `/api/health` 엔드포인트만 인증 제외
  - JWT에서 `user_id` 추출 → 요청 컨텍스트에 주입

- **WebSocket 인증**: 연결 시 쿼리 파라미터 `?token=<JWT>`로 인증

### 관리자 API

- `GET /api/admin/users` — 사용자 목록 조회
- `PATCH /api/admin/users/{id}` — 사용자 활성화/비활성화
- 관리자 판별: `users.is_admin = 1`

---

## 2. 멀티테넌트 데이터 분리

### 변경 대상 테이블

| 테이블 | 변경 | 이유 |
|--------|------|------|
| `account_state` | `user_id` PK로 변경 | 사용자별 잔고 |
| `positions` | `user_id` 추가 (PK: user_id + market) | 사용자별 포지션 |
| `orders` | `user_id` 추가 | 사용자별 거래 이력 |
| `daily_summary` | `user_id` 추가 (PK: user_id + date) | 사용자별 일일 수익률 |
| `risk_state` | `user_id` PK로 변경 | 사용자별 서킷브레이커 상태 |
| `signals` | 변경 없음 | ML 신호는 공유 |
| `candles` | 변경 없음 | 시장 데이터 공유 |
| `screening_log` | 변경 없음 | 스크리닝 공유 |

### 사용자별 설정 테이블

```sql
CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    initial_balance TEXT NOT NULL DEFAULT '5000000',
    max_position_pct TEXT NOT NULL DEFAULT '0.25',
    max_open_positions INTEGER NOT NULL DEFAULT 4,
    stop_loss_pct TEXT NOT NULL DEFAULT '0.03',
    take_profit_pct TEXT NOT NULL DEFAULT '0.08',
    trailing_stop_pct TEXT NOT NULL DEFAULT '0.015',
    max_daily_loss_pct TEXT NOT NULL DEFAULT '0.05',
    trading_enabled INTEGER NOT NULL DEFAULT 0
);
```

가입 시 `settings.yaml`의 기본값으로 자동 생성.

### App 구조 변경

```
[변경 전]
App
 └── account: PaperAccount (1개)
 └── risk_manager: RiskManager (1개)

[변경 후]
App
 └── shared: 시장 데이터 수집, ML, 스크리닝 (기존 그대로)
 └── user_accounts: dict[int, PaperAccount]  (user_id별)
 └── user_risk: dict[int, RiskManager]       (user_id별)
```

- 시장 데이터/ML 파이프라인: 기존처럼 하나만 실행
- 신호 발생 시: 모든 활성 사용자에 대해 각자의 RiskManager로 심사 → 각자의 PaperEngine으로 매매 실행
- 포지션 모니터링: 모든 사용자의 포지션을 순회하며 손절/익절 체크

### Repository 변경

기존 repo 메서드에 `user_id` 파라미터 추가:

```python
# 변경 전
async def get_positions(self) -> list[Position]:

# 변경 후
async def get_positions(self, user_id: int) -> list[Position]:
```

모든 쿼리에 `WHERE user_id = ?` 조건 추가.

---

## 3. Docker 배포 구성

### 컨테이너 구성

```
docker-compose.yml
├── app   — FastAPI 백엔드 (uvicorn)
└── web   — Nginx (React 정적 파일 서빙 + /api, /ws 리버스 프록시 + SSL)
```

### Dockerfile (멀티스테이지 빌드)

```
Stage 1: py-builder    — Python 의존성 설치 (uv)
Stage 2: web-builder   — Vite로 React 빌드
Stage 3: web           — Nginx + React 빌드 결과물 + SSL + 리버스 프록시
Stage 4: app           — FastAPI 런타임
```

### 빌드 & 배포 흐름

```bash
# 로컬에서 빌드 (linux/amd64)
docker build --platform linux/amd64 --target app -t agent-research-app:latest .
docker build --platform linux/amd64 --target web -t agent-research-web:latest .

# 이미지 저장
docker save agent-research-app:latest | gzip > agent-research-app.tar.gz
docker save agent-research-web:latest | gzip > agent-research-web.tar.gz

# 서버로 전송 & 로드
scp *.tar.gz user@192.168.102.150:~/
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz

# 실행
docker compose up -d
```

### docker-compose.yml

```yaml
services:
  app:
    image: agent-research-app:latest
    ports:
      - "${API_PORT:-8001}:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3

  web:
    image: agent-research-web:latest
    ports:
      - "${WEB_PORT:-443}:443"
      - "80:80"
    volumes:
      - ./deploy/ssl:/etc/ssl/app
    depends_on:
      app:
        condition: service_healthy
    restart: unless-stopped
```

포트: 기존 프로젝트(8000, 3000)와 겹치지 않도록 8001, 443 사용.

### Nginx 라우팅

```
https://<서버IP>/            → React SPA (정적 파일)
https://<서버IP>/api/*       → FastAPI (프록시)
https://<서버IP>/ws/*        → FastAPI WebSocket (프록시)
HTTP 80                      → HTTPS 301 리다이렉트
```

### 환경변수 (.env)

```
JWT_SECRET=<랜덤 시크릿>
INVITE_CODE=<초대코드>
ADMIN_EMAIL=<관리자 이메일>
API_PORT=8001
WEB_PORT=443
```

### 데이터 영속성 (Docker 볼륨)

- `./data:/app/data` — SQLite DB + ML 모델
- `./config:/app/config` — settings.yaml
- `./deploy/ssl:/etc/ssl/app` — SSL 인증서

---

## 4. 프론트엔드 변경

### 새로운 페이지

| 페이지 | 경로 | 설명 |
|--------|------|------|
| 로그인 | `/login` | 이메일 + 비밀번호 |
| 회원가입 | `/register` | 이메일 + 비밀번호 + 닉네임 + 초대코드 |

### 인증 상태 관리

- `useAuth` 훅: 로그인 상태, 토큰 관리, 자동 refresh
- 토큰을 `localStorage`에 저장
- `useApi` 훅 수정: 모든 요청에 `Authorization: Bearer <token>` 헤더 자동 첨부
- 401 응답 시 → refresh 시도 → 실패하면 `/login`으로 리다이렉트

### 라우팅

- 비인증: `/login`, `/register`만 접근 가능, 나머지는 `/login`으로 리다이렉트
- 인증: 기존 페이지 모두 접근 가능, `/login`, `/register` 접근 시 Dashboard로 리다이렉트

### 기존 페이지 변경

- **System**: 사용자 본인의 매매 설정만 수정 가능, 글로벌 설정은 관리자만
- **Dashboard**: 본인의 포트폴리오만 표시
- **Exchange**: 본인의 포지션/주문만 표시
- **사이드바**: 닉네임 표시 + 로그아웃 버튼

### 관리자 전용 UI

- System 페이지에 **사용자 관리 탭**: 사용자 목록, 활성화/비활성화
- 글로벌 설정(스크리닝, ML, collector) 수정 권한

---

## 5. 보안

- **CORS**: 배포 시 서버 IP만 허용
- **Rate limiting**: 로그인 시도 IP당 5회/분
- **비밀번호**: bcrypt 해싱, 최소 8자
- **JWT**: HS256 서명, secret은 환경변수
- **WebSocket**: 연결 시 `?token=<JWT>` 쿼리 파라미터로 인증
- **Health**: `GET /api/health` 인증 불요 (Docker healthcheck용)

### 에러 코드

| 상황 | 응답 |
|------|------|
| 인증 실패 | 401 Unauthorized |
| 권한 부족 | 403 Forbidden |
| 초대코드 불일치 | 400 Bad Request |
| 비활성 계정 | 403 Forbidden |

---

## 6. 추가 의존성

### Python

- `bcrypt` — 비밀번호 해싱
- `PyJWT` — JWT 토큰 생성/검증

### 프론트엔드

- 추가 의존성 없음 (기존 React + fetch로 충분)

---

## 변경하지 않는 영역

- ML 파이프라인 (FeatureBuilder, predictor, trainer)
- 시장 데이터 수집 (collector, screener)
- 이벤트 버스 / 스케줄러 구조
- 6계층 아키텍처 규칙
- Decimal 금융 계산 규칙
