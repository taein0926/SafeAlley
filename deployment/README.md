# 서버 배포

로컬과 서버는 별도 환경입니다. Git push는 소스만 갱신하며 컨테이너/DB/모델/환경변수까지
배포하지 않습니다. 실제 배포 commit과 설정은 서버에서 따로 확인하세요.
비밀번호·API 키·SSH 개인키·DB 백업은 저장소/소스 ZIP에 넣지 않습니다.

## 1. VM 앱 + GPU Ollama (현재 분리 구성)

VM에서 frontend/backend/database/weather를 실행하고 기존 GPU 호스트 Ollama와 별도 GPU Whisper 서비스를 사용합니다.
루트 docker-compose.yml + deployment/compose.vm.override.yml 조합입니다.
manage.py는 아래 단일 GPU 대안 전용이므로 VM override 작업에 혼용하지 않습니다.

```text
브라우저 → 승인된 포워딩/HTTPS proxy → VM frontend(Nginx)
                                        └→ backend(FastAPI) → PostGIS
                                                          → host gateway:11435 → SSH 터널 → GPU Ollama
                                                          → host gateway:11436 → SSH 터널 → GPU Whisper
                            weather 배치 → KMA/KASI → PostGIS
브라우저 → 외부 OSM 타일 (직접 요청)
```

- VM 공개 앱 포트는 기본 127.0.0.1:8080; backend/DB 공개 포트는 제거합니다.
- 터널은 승인된 GPU Ollama loopback 11434를 Docker host gateway 11435로 연결합니다.
  gateway 주소/방화벽/SSH 키·서버 지문·재연결 방식은 실제 서버에 맞춰 관리합니다.
- backend 설정 주소는 http://host.docker.internal:11435, 기본 모델 qwen3.6:35b.
- GPU 서버의 기존 Ollama/모델/다른 서비스는 임의로 재시작하거나 교체하지 않습니다.
- 음성은 VM FastAPI에서만 받습니다. GPU Whisper는 GPU 서버의 127.0.0.1에만 바인딩하고
  별도 제한된 SSH 키/터널로 연결합니다. 터널이 일시 중단되면 VM의 CPU Whisper로 대체합니다.
  `backend/app/services/gpu_stt_server.py`는 GPU 호스트에서 별도 Python 환경으로 실행하며
  `STT_MODEL=small`, `STT_MODEL_DIR`와 CUDA 12/cuDNN 9 런타임을 사용합니다.
- 루트 비공개 .env에 서버 DB 비밀번호, 날씨 키, 실제 모델을 설정합니다.
  Jev는 별도 승인 시에만 JEV_PREVIEW_ENABLED/TYPESAFE_API_KEY를 넣습니다.

설정 검증과 빌드 예시(서버의 해당 release 디렉터리에서):

```bash
docker compose --env-file .env -p safealley-deploy -f docker-compose.yml -f deployment/compose.vm.override.yml config --quiet
docker compose --env-file .env -p safealley-deploy -f docker-compose.yml -f deployment/compose.vm.override.yml build backend frontend weather
```

신규 설치 순서: 빌드 → 빈 DB → 승인된 공간 백업 복원 → migration → 히트맵 → 앱 시작.
운영 중인 DB에는 restore를 덮어쓰지 않습니다. migration head는 0016입니다.
기존 환경 업데이트는 먼저 백업/이전 release·설정·이미지를 보관한 뒤 수행합니다.

데이터가 준비된 환경의 실행/점검:

```bash
docker compose --env-file .env -p safealley-deploy -f docker-compose.yml -f deployment/compose.vm.override.yml up -d
docker compose --env-file .env -p safealley-deploy -f docker-compose.yml -f deployment/compose.vm.override.yml ps
curl -f http://127.0.0.1:8080/api/health
```

직원 PC의 localhost는 VM이 아닙니다. 담당자가 승인한 SSH -L 포워딩/HTTPS proxy로 접속합니다.
외부 공개 포트/주소를 문서 예시만 보고 새로 열지 않습니다.

### 노트북 개발 환경에서 GPU 음성 사용

로컬 Docker는 기본적으로 CPU 음성 인식을 사용합니다. 승인된 GPU 서버에 Whisper가
설치되어 있다면, 노트북 사용자 전용 SSH 키를 GPU 서버의 Whisper 포트에만 허용하고
로컬에서 사용할 때만 `deployment/local-gpu-stt-tunnel.ps1`을 실행해
`127.0.0.1:11436` 터널을 엽니다. 서버 접속에는 노트북 터널이 필요하지 않습니다.
키와 서버 지문은 사용자 `.ssh`에 두고 저장소에 넣지 않습니다. 로컬 비공개 `.env`에는
`STT_REMOTE_URL=http://host.docker.internal:11436`을 설정합니다. GPU 연결이 끊기면
VM과 동일하게 로컬 Docker 백엔드의 CPU Whisper로 대체됩니다. 터널이 살아 있는지는
`http://127.0.0.1:11436/health`로, 실제 음성 응답의 `device`가 `cuda`인지로 확인합니다.

## 2. 단일 GPU 서버 대안

deployment/compose.yml은 GPU Ollama 컨테이너까지 같은 프로젝트에 구성하는 별도 설치 방식입니다.
deployment/manage.py는 이 Compose와 deployment/.env를 사용하고 프로젝트 이름은 safealley-deploy입니다.
Linux NVIDIA 드라이버/Container Toolkit, Docker Compose, Python 3.10+가 필요합니다.
서버에 이미 Ollama가 있다면 위 분리 방식과 이 대안을 구분해 운영자가 결정합니다.

```bash
cp deployment/.env.example deployment/.env
chmod 600 deployment/.env
# 편집기로 서버용 비밀 설정을 작성합니다.
python3 deployment/manage.py check
python3 deployment/manage.py build
python3 deployment/manage.py database
python3 deployment/manage.py restore --file /approved-transfer/safealley.dump --confirm safealley-deploy
python3 deployment/manage.py migrate
python3 deployment/manage.py models
python3 deployment/manage.py heatmap
python3 deployment/manage.py start
python3 deployment/manage.py verify
```

approved-transfer 경로는 실제 승인된 백업으로 바꿉니다.
체크섬/빈 DB/앱 정지 검사를 통과해야 복원하며 --clean으로 삭제하지 않습니다.
POSTGRES_PASSWORD는 24자 이상 새 임의값, OLLAMA_IMAGE는 운영자가 승인한 고정 tag/digest를 사용합니다.
대안 설정의 기본 모델 qwen3:4b는 분리 구성의 qwen3.6:35b와 다릅니다.
models는 모델 준비 단계이며 서비스 시작만으로 모델이 자동 준비되지는 않습니다.

## 전달·백업

저장소 루트의 `SafeAlley-deploy.tar.gz`가 소스 전달본입니다.
소스 tar.gz, 비공개 DB dump+체크섬, 서버 비공개 .env를 구분합니다.
tar.gz는 Docker 이미지·공간 DB·원본·모델·비밀값을 포함한 오프라인 설치본이 아닙니다.

```powershell
# 개발 PC에서 필요한 경우만. 기존 대상은 덮어쓰지 않습니다.
python deployment/package.py --ref HEAD --output output/deployment/SafeAlley-deploy.tar.gz
python deployment/manage.py backup --source-local --exclude-feedback --file output/private-transfer/safealley.dump
```

package.py는 커밋된 Git 파일만 포함합니다. 미커밋 변경은 배포되지 않으며
`--ref`로 소스 커밋을 고정합니다. release.json의 base_commit/파일별 체크섬과
아카이브 체크섬을 확인합니다. .env.example과 NOTICE.md는 포함하고 실제 .env·DB·모델은 제외합니다.
추천/선택 기록 제외는 개발 이관용 선택사항이며
정식 운영 전체 백업에서는 --exclude-feedback을 사용하지 않습니다.
DB dump는 암호화되지 않으므로 별도 접근권한/전송 보호가 필요합니다.

기존 VM 갱신은 파일 SHA256 확인 → 새 `main-커밋` 디렉터리에 `SafeAlley/` 내용 추출 →
기존 `.env`와 `vm.override.yml` 복사 → DB 백업·이전 이미지 보관 → backend/frontend 빌드·교체 →
health/공간 API/지도 타일/화면 확인 순서입니다. DB·weather 컨테이너와 GPU 모델은 재생성하지 않습니다.
새 버전 검증 후 이전 전달용 tar.gz만 정리하며, 이전 소스 폴더·백업·이미지는 롤백용으로 남깁니다.
저장소의 전달본 커밋과 아카이브 내부 release.json의 소스 base_commit은 구분합니다.

frontend 이미지 빌드는 공개 정적 파일의 권한을 디렉터리 755/파일 644로 정규화합니다.
서버의 제한적인 umask로 추출된 이미지도 Nginx worker가 읽을 수 있어야 합니다.
운영 검증에는 `frontend/tests/welcome-intro.e2e.cjs`도 포함해 첫 안내창의 로고 8개를
실제로 디코딩하는지 확인합니다. `/healthz` 성공만으로 이미지 접근 권한은 검증되지 않습니다.

## 검증·운영

[전체 테스트](../docs/testing.md), [배포 점검](../docs/deployment-checklist.md)을 따릅니다.
소스 테스트 통과는 실제 GPU/음성/포워딩/HTTPS 검증의 대체가 아닙니다.
실제 요청 후 GPU 호스트 ollama ps, 대상 DB·migration·정밀 시설 좌표·타일·날씨를 확인합니다.
proxy는 스트림 buffering off, query 읽기 timeout 660초, 음성 8MB/180초를 유지합니다.
마이크는 localhost 개발 또는 HTTPS에서 사용합니다.

정지/백업/이전 이미지 보관과 복원 연습을 수행합니다. down -v로 볼륨을 지우지 않습니다.
앱 이미지 롤백은 DB migration 롤백이 아니며 기존 운영 DB를 자동 downgrade/교체하지 않습니다.
