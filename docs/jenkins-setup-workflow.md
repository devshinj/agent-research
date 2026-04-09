# Jenkins CI/CD 환경 구성 워크플로우

> crypto-paper-trader 프로젝트 전용 Jenkins 파이프라인 구축 가이드

---

## 1. 전제 조건

### 1.1 현재 프로젝트 상태

| 항목 | 상태 |
|------|------|
| Git 원격 저장소 | `https://github.com/devshinj/agent-research.git` |
| 배포 대상 서버 | `192.168.102.150` |
| Docker 이미지 | `agent-research-app`, `agent-research-web` |
| 테스트 체계 | unit(45) + integration(4) + structural(2) |
| 코드 품질 도구 | ruff, mypy, pre-commit |
| 패키지 매니저 | uv (Python), npm (Frontend) |

### 1.2 필요 인프라

- Jenkins 서버를 실행할 머신 (배포 서버와 동일해도 무방)
- Jenkins 서버 → GitHub 네트워크 접근
- Jenkins 서버 → 배포 서버(`192.168.102.150`) SSH 접근
- Docker 설치 (이미지 빌드용)

---

## 2. Jenkins 서버 설치

### 방법 A: Docker로 실행 (권장)

```bash
# Jenkins 데이터 디렉토리 생성
mkdir -p /opt/jenkins/data

# Docker-in-Docker 지원 Jenkins 실행
docker run -d \
  --name jenkins \
  --restart unless-stopped \
  -p 8080:8080 \
  -p 50000:50000 \
  -v /opt/jenkins/data:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  jenkins/jenkins:lts

# 초기 관리자 비밀번호 확인
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

> Docker 소켓 마운트(`/var/run/docker.sock`)는 Jenkins 내부에서 Docker 빌드를 실행하기 위한 것.

### 방법 B: 직접 설치 (Linux)

```bash
# Java 17 설치
sudo apt install -y openjdk-17-jdk

# Jenkins 저장소 추가 및 설치
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | sudo tee /usr/share/keyrings/jenkins-keyring.asc
echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list
sudo apt update && sudo apt install -y jenkins

sudo systemctl enable --now jenkins
```

---

## 3. Jenkins 초기 설정

### 3.1 웹 UI 접근

1. 브라우저에서 `http://<jenkins-server>:8080` 접속
2. 초기 비밀번호 입력
3. "Install suggested plugins" 선택

### 3.2 필수 플러그인 설치

**Manage Jenkins → Plugins → Available plugins**에서 설치:

| 플러그인 | 용도 |
|---------|------|
| Pipeline | Jenkinsfile 파이프라인 지원 |
| Docker Pipeline | Docker 빌드 스텝 |
| Git | 소스코드 체크아웃 |
| Credentials Binding | 비밀값 바인딩 |
| SSH Agent | 배포 서버 SSH 접속 |
| Workspace Cleanup | 빌드 후 워크스페이스 정리 |
| Warnings Next Generation | ruff/mypy 경고 리포트 (선택) |

### 3.3 빌드 도구 설치 (Jenkins 에이전트)

Jenkins가 빌드를 실행할 머신에 아래 도구를 설치:

```bash
# Python 3.12
sudo apt install -y python3.12 python3.12-venv

# uv (Python 패키지 매니저)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Docker
sudo apt install -y docker.io
sudo usermod -aG docker jenkins
```

---

## 4. Credentials 등록

**Manage Jenkins → Credentials → System → Global credentials**

| ID | 종류 | 값 | 용도 |
|----|------|-----|------|
| `github-token` | Username with password | GitHub PAT | Git 체크아웃 |
| `deploy-ssh-key` | SSH Username with private key | 배포 서버 SSH 키 | 배포용 SCP/SSH |
| `env-file` | Secret file | `.env` 내용 | 런타임 환경변수 |
| `jwt-secret` | Secret text | JWT 서명 키 | 빌드 시 주입 |
| `gemini-api-key` | Secret text | Gemini API 키 | 빌드 시 주입 |

> `.env`에 포함된 민감 값: `JWT_SECRET`, `INVITE_CODE`, `ADMIN_EMAIL`, `GEMINI_API_KEY`

---

## 5. Jenkinsfile 파이프라인

프로젝트 루트에 `Jenkinsfile`을 생성합니다.

### 5.1 파이프라인 단계 흐름

```
Checkout
  → Install (Python + Node.js 병렬)
    → Quality Gate (Lint + Type Check + Structural Tests 병렬)
      → Unit Tests
        → Integration Tests
          → Docker Build (app + web 이미지)
            → Deploy (배포 서버로 전송 및 실행)
```

### 5.2 Jenkinsfile 내용

```groovy
pipeline {
    agent any

    environment {
        SERVER_IP    = '192.168.102.150'
        WEB_PORT     = '3001'
        API_PORT     = '8002'
        VITE_API_URL = "http://${SERVER_IP}:${WEB_PORT}"
        VITE_WS_URL  = "ws://${SERVER_IP}:${WEB_PORT}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            parallel {
                stage('Python') {
                    steps {
                        sh 'uv sync'
                    }
                }
                stage('Node.js') {
                    steps {
                        dir('src/ui/frontend') {
                            sh 'npm ci'
                        }
                    }
                }
            }
        }

        stage('Quality Gate') {
            parallel {
                stage('Lint') {
                    steps {
                        sh 'uv run ruff check src/'
                    }
                }
                stage('Format Check') {
                    steps {
                        sh 'uv run ruff format --check src/'
                    }
                }
                stage('Type Check') {
                    steps {
                        sh 'uv run mypy src/'
                    }
                }
                stage('Structural Tests') {
                    steps {
                        sh 'uv run pytest tests/structural/ -x -q'
                    }
                }
            }
        }

        stage('Unit Tests') {
            steps {
                sh 'uv run pytest tests/unit/ -x -q --tb=short'
            }
        }

        stage('Integration Tests') {
            steps {
                sh 'uv run pytest tests/integration/ -x -q --tb=short'
            }
        }

        stage('Docker Build') {
            steps {
                sh """
                    docker build --platform linux/amd64 \
                        --target app \
                        -t agent-research-app:latest \
                        -f deploy/Dockerfile .

                    docker build --platform linux/amd64 \
                        --target web \
                        -t agent-research-web:latest \
                        --build-arg VITE_API_URL=${VITE_API_URL} \
                        --build-arg VITE_WS_URL=${VITE_WS_URL} \
                        -f deploy/Dockerfile .
                """
            }
        }

        stage('Save Images') {
            steps {
                sh """
                    docker save agent-research-app:latest | gzip > deploy/agent-research-app.tar.gz
                    docker save agent-research-web:latest | gzip > deploy/agent-research-web.tar.gz
                """
            }
        }

        stage('Deploy') {
            steps {
                sshagent(credentials: ['deploy-ssh-key']) {
                    // 이미지 전송
                    sh """
                        scp deploy/agent-research-app.tar.gz deploy/agent-research-web.tar.gz \
                            user@${SERVER_IP}:/opt/agent-research/

                        scp deploy/docker-compose.yml \
                            user@${SERVER_IP}:/opt/agent-research/
                    """

                    // .env 파일 전송
                    withCredentials([file(credentialsId: 'env-file', variable: 'ENV_FILE')]) {
                        sh "scp \$ENV_FILE user@${SERVER_IP}:/opt/agent-research/.env"
                    }

                    // 원격 서버에서 배포 실행
                    sh """
                        ssh user@${SERVER_IP} '
                            cd /opt/agent-research
                            docker load -i agent-research-app.tar.gz
                            docker load -i agent-research-web.tar.gz
                            docker compose down
                            docker compose up -d
                            docker compose ps
                        '
                    """
                }
            }
        }
    }

    post {
        success {
            echo "배포 완료: http://${SERVER_IP}:${WEB_PORT}"
        }
        failure {
            echo '빌드 또는 배포 실패'
            // 슬랙/이메일 알림 추가 가능
        }
        always {
            cleanWs()
        }
    }
}
```

---

## 6. Jenkins Job 생성

1. **New Item** → 이름: `crypto-paper-trader` → **Pipeline** 선택
2. **Pipeline** 섹션:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/devshinj/agent-research.git`
   - Credentials: `github-token`
   - Branch: `*/main`
   - Script Path: `Jenkinsfile`
3. **Build Triggers** (택 1):
   - **GitHub hook trigger for GITScm polling** — push 시 자동 빌드
   - **Poll SCM**: `H/5 * * * *` — 5분마다 변경 확인
4. **저장**

---

## 7. GitHub Webhook 설정 (자동 트리거)

1. GitHub 저장소 → **Settings → Webhooks → Add webhook**
2. Payload URL: `http://<jenkins-server>:8080/github-webhook/`
3. Content type: `application/json`
4. Events: **Just the push event**
5. Active: 체크

> Jenkins 서버가 외부에서 접근 가능해야 함. 내부망이면 Poll SCM 사용.

---

## 8. 배포 서버 사전 준비

배포 대상 서버(`192.168.102.150`)에 필요한 사전 작업:

```bash
# Docker 및 Docker Compose 설치
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker

# 애플리케이션 디렉토리 생성
sudo mkdir -p /opt/agent-research
sudo chown $USER:$USER /opt/agent-research

# Jenkins 서버의 SSH 공개키 등록
mkdir -p ~/.ssh
echo "<jenkins-서버-공개키>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## 9. 파이프라인 실행 순서 요약

```
┌─────────────────────────────────────────────────────────────┐
│  개발자 PC                                                   │
│  git push origin main                                       │
└──────────────┬──────────────────────────────────────────────┘
               │ GitHub Webhook / Poll SCM
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Jenkins 서버 (파이프라인 실행)                                │
│                                                             │
│  1. Checkout ─────────────────── Git clone                  │
│  2. Install ──────────────────── uv sync + npm ci           │
│  3. Quality Gate (병렬) ──────── ruff + mypy + structural   │
│  4. Unit Tests ───────────────── pytest tests/unit/         │
│  5. Integration Tests ────────── pytest tests/integration/  │
│  6. Docker Build ─────────────── app + web 이미지            │
│  7. Save Images ──────────────── tar.gz 압축                │
│  8. Deploy ───────────────────── SCP + docker compose up    │
└──────────────┬──────────────────────────────────────────────┘
               │ SCP + SSH
               ▼
┌─────────────────────────────────────────────────────────────┐
│  배포 서버 (192.168.102.150)                                 │
│                                                             │
│  ┌──────────┐     ┌──────────────┐                          │
│  │ Nginx    │────▶│ FastAPI      │                          │
│  │ :3001/80 │     │ :8000        │                          │
│  │ (web)    │     │ (app)        │                          │
│  └──────────┘     └──────────────┘                          │
│       │                  │                                   │
│       ▼                  ▼                                   │
│  React SPA          SQLite + ML Models                      │
│  /usr/share/nginx   /app/data (volume)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. 환경변수 목록

Jenkins에서 관리해야 할 환경변수 전체 목록:

| 변수 | 설명 | 파이프라인 단계 | 관리 방식 |
|------|------|----------------|----------|
| `JWT_SECRET` | JWT 토큰 서명 키 | Deploy | Jenkins Secret text |
| `INVITE_CODE` | 회원가입 초대 코드 | Deploy | Jenkins Secret text |
| `ADMIN_EMAIL` | 관리자 이메일 | Deploy | Jenkins Secret text |
| `GEMINI_API_KEY` | Google Gemini API 키 | Deploy | Jenkins Secret text |
| `API_PORT` | FastAPI 포트 | Deploy | Jenkinsfile 환경변수 |
| `WEB_PORT` | Nginx 포트 | Deploy | Jenkinsfile 환경변수 |
| `CORS_ORIGINS` | CORS 허용 오리진 | Deploy | Jenkinsfile 환경변수 |
| `VITE_API_URL` | 프론트엔드 API URL | Docker Build | Jenkinsfile 환경변수 |
| `VITE_WS_URL` | 프론트엔드 WebSocket URL | Docker Build | Jenkinsfile 환경변수 |

---

## 11. 트러블슈팅

### Docker 권한 오류
```
Got permission denied while trying to connect to the Docker daemon socket
```
→ Jenkins 사용자를 docker 그룹에 추가: `sudo usermod -aG docker jenkins && sudo systemctl restart jenkins`

### uv 명령어를 찾을 수 없음
→ Jenkins 빌드 환경에서 PATH 설정:
```groovy
environment {
    PATH = "/home/jenkins/.local/bin:${env.PATH}"
}
```

### npm ci 메모리 부족
→ Node.js 메모리 제한 증가:
```groovy
environment {
    NODE_OPTIONS = '--max-old-space-size=4096'
}
```

### mypy 캐시 충돌
→ `cleanWs()` 또는 mypy 캐시 삭제:
```groovy
sh 'rm -rf .mypy_cache'
```

### SSH 연결 거부
→ 배포 서버에 Jenkins SSH 공개키 등록 확인, 방화벽 포트 22 확인
