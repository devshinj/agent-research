# Docker Build & Deploy Guide

## 아키텍처

```
[브라우저] :3001 → [Nginx(web)] → :8000 [FastAPI(app)]
                    │                      │
              React SPA 서빙         수집기 / 전략 / WebSocket
              /api/* 리버스 프록시    SQLite (app-data 볼륨)
              /ws/*  WS 프록시       ML 모델 (app-data 볼륨)
```

## 서버 디렉토리 구조

```
~/sjs-crypto-paper-trader/
├── docker-compose.yml
├── .env
├── agent-research-app.tar.gz
└── agent-research-web.tar.gz
```

---

## 1. 로컬에서 빌드 (Windows PowerShell)

```powershell
# API
docker build --platform linux/amd64 --target app -t agent-research-app:latest -f deploy/Dockerfile .

# Web
docker build --platform linux/amd64 --target web -t agent-research-web:latest --build-arg VITE_API_URL=http://192.168.102.150:3001 --build-arg VITE_WS_URL=ws://192.168.102.150:3001 -f deploy/Dockerfile .
```

## 2. 이미지 저장 & 서버 전송

```bit bash
docker save agent-research-app:latest | gzip > agent-research-app.tar.gz
docker save agent-research-web:latest | gzip > agent-research-web.tar.gz

scp agent-research-*.tar.gz user@192.168.102.150:~/sjs-crypto-paper-trader/
```

최초 1회만 추가 전송:
```powershell
scp deploy/docker-compose.yml user@192.168.102.150:~/sjs-crypto-paper-trader/
scp deploy/.env.example user@192.168.102.150:~/sjs-crypto-paper-trader/.env
```

## 3. 서버 초기 설정 (최초 1회)

```bash
cd ~/sjs-crypto-paper-trader

# .env 편집
vi .env
# JWT_SECRET → 랜덤 문자열로 변경 (필수)
# INVITE_CODE → 회원가입 초대 코드
# GEMINI_API_KEY → Gemini API 키
```

## 4. 서버에서 실행

```bash
cd ~/sjs-crypto-paper-trader
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz
docker compose up -d
```

접속: **http://192.168.102.150:3001**

## 5. 운영 명령어

```bash
# 로그 확인
docker compose logs -f app
docker compose logs -f web

# 상태 확인
docker compose ps

# 재시작
docker compose restart app

# 중지
docker compose down
```

## 6. 업데이트 배포

로컬에서 이미지 빌드 후:

```bash
# 서버에서
cd ~/sjs-crypto-paper-trader
docker compose down
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz
docker compose up -d
```

---

## 환경변수 (.env)

| 변수 | 설명 | 필수 |
|------|------|:----:|
| `JWT_SECRET` | JWT 서명 키 (랜덤 문자열) | O |
| `INVITE_CODE` | 회원가입 초대 코드 | O |
| `ADMIN_EMAIL` | 관리자 이메일 | O |
| `GEMINI_API_KEY` | Gemini API 키 | O |
| `API_PORT` | API 외부 포트 (기본: 8002) | |
| `WEB_PORT` | 웹 외부 포트 (기본: 3001) | |
| `CORS_ORIGINS` | 허용 오리진 (기본: *) | |

## 데이터 영속성

- `app-data` Docker named volume에 SQLite DB와 ML 모델 저장
- `docker compose down`해도 데이터 유지
- 볼륨 완전 삭제: `docker volume rm sjs-crypto-paper-trader_app-data`
