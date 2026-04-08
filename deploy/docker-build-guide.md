# Docker Build & Deploy Guide

## 로컬에서 빌드

### API
docker build --platform linux/amd64 --target app -t agent-research-app:latest -f deploy/Dockerfile .

### Web
docker build --platform linux/amd64 --target web -t agent-research-web:latest \
  --build-arg VITE_API_URL=https://192.168.102.150 \
  --build-arg VITE_WS_URL=wss://192.168.102.150 \
  -f deploy/Dockerfile .

## 이미지 저장 & 전송

docker save agent-research-app:latest | gzip > agent-research-app.tar.gz
docker save agent-research-web:latest | gzip > agent-research-web.tar.gz

scp agent-research-*.tar.gz user@192.168.102.150:~/agent-research/

## 서버에서 실행

cd ~/agent-research
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz

# 초기 설정 (최초 1회)
cp deploy/.env.example .env
# .env 편집: JWT_SECRET, INVITE_CODE 설정
bash deploy/ssl/generate-cert.sh

# 실행
docker compose -f deploy/docker-compose.yml up -d

# 로그 확인
docker compose -f deploy/docker-compose.yml logs -f app

# 업데이트
docker compose -f deploy/docker-compose.yml down
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz
docker compose -f deploy/docker-compose.yml up -d
