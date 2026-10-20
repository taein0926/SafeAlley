# 서버 배포

로컬과 서버는 별도 환경입니다. Git push는 소스만 갱신하며 컨테이너/DB/모델/환경변수까지
배포하지 않습니다. 실제 배포 commit과 설정은 서버에서 따로 확인하세요.
비밀번호·API 키·SSH 개인키·DB 백업은 저장소/소스 ZIP에 넣지 않습니다.

## 1. VM 앱 + GPU Ollama (현재 분리 구성)

VM에서 frontend/backend/database/weather를 실행하고 기존 GPU 호스트 Ollama와 별도 GPU Whisper 서비스를 사용합니다.
신규 구성 템플릿은 루트 docker-compose.yml + deployment/compose.vm.override.yml입니다.
2026-10-20 기존 VM은 아래 고정 `runtime/compose.json` 구조로 전환했습니다.
템플릿을 현재 VM 위에 그대로 적용하지 않습니다.
manage.py는 아래 단일 GPU 대안 전용이므로 VM override 작업에 혼용하지 않습니다.

```text
브라우저 HTTPS :21802 → 승인된 TCP 포워딩 → VM :8081 → frontend Nginx :80 (TLS)
                                        └→ backend(FastAPI) → PostGIS
                                                          → host gateway:11435 → SSH 터널 → GPU Ollama
                                                          → host gateway:11436 → SSH 터널 → GPU Whisper
                            weather 배치 → KMA/KASI → PostGIS
브라우저 → 외부 OSM 타일 (직접 요청)
```

- 현재 VM은 `0.0.0.0:8081 → frontend:80`이며 Nginx가 그 포트에서 HTTPS를 받습니다.
  외부 주소는 `https://ltmetric-pms.synology.me:21802/`입니다. backend/DB는 호스트에 공개하지 않습니다.
  템플릿의 `127.0.0.1:8080`은 신규 설치용 안전 기본값이지 현재 운영 포트가 아닙니다.
- 자체 서명 인증서는 `private/tls-f6b47f3/`에 있습니다. 인증서·개인키·Nginx 설정을 삭제하지 않습니다.
  HTTP 요청은 Nginx error 497 처리로 외부 HTTPS 주소로 이동합니다. 인증서를 신뢰하지 않는
  브라우저는 경고를 표시합니다. 예외 접속 후 마이크를 확인하고, 차단되면 인증서 신뢰 등록을 검토합니다.
  현재 인증서 만료는 2027-10-20 UTC이며 갱신과 브라우저 테스트가 필요합니다.
- 터널은 승인된 GPU Ollama loopback 11434를 Docker host gateway 11435로 연결합니다.
  gateway 주소/방화벽/SSH 키·서버 지문·재연결 방식은 실제 서버에 맞춰 관리합니다.
- backend 설정 주소는 http://host.docker.internal:11435입니다. 저장소 템플릿의
  기본 모델은 `qwen3.6:35b`지만 2026-10-16 확인한 실제 VM 모델은 `gemma4:26b`입니다.
  모델 값은 매 배포마다 적용된 비공개 설정과 backend 환경에서 확인합니다.
- GPU 서버의 기존 Ollama/모델/다른 서비스는 임의로 재시작하거나 교체하지 않습니다.
- 음성은 VM FastAPI에서만 받습니다. GPU Whisper는 GPU 서버의 127.0.0.1에만 바인딩하고
  별도 제한된 SSH 키/터널로 연결합니다. 터널이 일시 중단되면 VM의 CPU Whisper로 대체합니다.
  `backend/app/services/gpu_stt_server.py`는 GPU 호스트에서 별도 Python 환경으로 실행하며
  `STT_MODEL=small`, `STT_MODEL_DIR`와 CUDA 12/cuDNN 9 런타임을 사용합니다.
- 신규 템플릿은 비공개 .env, 현재 VM은 private/service-env/에 DB 비밀번호·날씨 키·실제 모델을 설정합니다.
  Jev는 별도 승인 시에만 JEV_PREVIEW_ENABLED/TYPESAFE_API_KEY를 넣습니다.

### 현재 VM의 한 명령 업데이트

```text
~/safealley-deploy/
  runtime/    compose.json, update.py, state.json, database/init/
  private/    service-env/, build-args.json, TLS, DB/설정 복구 백업
  packages/   현재·직전 소스 tar.gz와 체크섬
```

네 컨테이너의 Compose 기준 경로는 항상 `runtime`입니다. 소스는 임시 폴더에서 빌드하고
성공/실패 후 제거합니다. 실행 코드는 이미지 안에 있으며 소스를 보려면 압축본을 해제합니다.
업데이트 도구는 `deployment/vm_update.py`를 서버 `runtime/update.py`에 설치한 것입니다.
GitLab 자동 배포나 로컬 commit 자동 push는 구성하지 않습니다.
서버 도구는 Python 3.10+와 raw env_file을 지원하는 Docker Compose가 필요하며 현재 VM은
Compose 5.6.0에서 검증했습니다. 기존 runtime 환경을 채택한 업데이트용 도구이지 빈 서버 설치 프로그램은 아닙니다.

노트북에서 커밋을 고정해 만든 tar.gz와 `.sha256`을 함께 업로드합니다.

```powershell
scp -P 22203 "새배포파일.tar.gz" "새배포파일.tar.gz.sha256" ltmetric@ltmetric-pms.synology.me:/home/ltmetric/safealley-deploy/packages/
```

VM에서 실제 업로드한 파일명을 지정합니다.

```bash
python3 ~/safealley-deploy/runtime/update.py update --archive ~/safealley-deploy/packages/새배포파일.tar.gz
python3 ~/safealley-deploy/runtime/update.py status
```

도구는 체크섬·manifest·파일 경로 검증 → DB 백업·검증 → 변경된 backend/frontend/weather
이미지 빌드 → Nginx TLS 설정 검사 → 앱 컨테이너 교체 → HTTPS/API/정적 파일·GPU 연결을 확인합니다.
database 컨테이너·기존 데이터 볼륨·외부 포트·터널·GPU 서비스는 일반 업데이트에서 교체하지 않습니다.
같은 커밋은 검증 후 변경 없이 종료하며 `--rebuild`는 동일 버전의 재빌드·교체를 명시적으로 요청합니다.

빌드 실패는 기존 컨테이너를 교체하지 않습니다. 교체 후 검사 실패는 DB revision이 그대로인
경우에만 이전 앱 이미지를 복구합니다. migration 변경 배포에서 교체가 시작된 뒤 실패하면
부분 적용 가능성 때문에 자동 앱 롤백도 중단합니다. DB 자동 복원·downgrade·볼륨 삭제는 하지 않습니다.
실패 로그·DB dump는 `private/updates/`에 보관합니다. 출력에 비밀번호나 키를 표시하지 않습니다.
`runtime/pending.json`이 남으면 다음 업데이트를 차단합니다. 파일을 임의 삭제하지 말고 실패 원인을 확인합니다.

기존 migration 변경/삭제는 거절합니다. 새 migration은 검토 후 `--allow-migration`을 명시해야 합니다.
DB가 변경된 뒤 실패하면 자동 앱 롤백도 중단합니다. 해당 백업과 schema 호환성을 별도 검토하세요.
`docker-compose.yml`, DB 초기화 파일, `frontend/nginx.conf`가 바뀐 압축본은 고정 운영 설정과의
의미상 병합이 필요하므로 자동 배포를 거절합니다. 이는 새 포트/설정이 운영 환경을 덮어쓰지 않게 하는 안전장치입니다.

최근 앱 업데이트를 되돌릴 때(해당 DB revision이 유지된 경우만):

```bash
python3 ~/safealley-deploy/runtime/update.py rollback
```

운영 환경변수는 `private/service-env/backend.env`, `weather.env`, `database.env` 등입니다.
최초 전환 시 기존 실제 값을 복사했으며 Compose의 raw env_file 방식으로 해석합니다.
키 값을 문서·명령 인수·Git에 쓰지 않습니다. 일반 업데이트는 이 파일을 변경하지 않습니다.
프론트 빌드 설정은 `private/build-args.json`입니다. VITE_*는 브라우저에 공개됩니다.
운영 설정을 수정할 때는 관련 서비스를 `runtime/compose.json` 기준으로 재생성하고 다시 검증합니다.

새 커밋 배포 성공 후 updater가 관리하는 packages는 현재·직전 버전만 유지합니다.
완료된 업데이트 체크포인트는 최근 2개를 유지하며, 최초 전환 백업·기존 수동 백업·실패 기록은
자동으로 삭제하지 않습니다. Docker 전체 prune은 수행하지 않습니다.
현재·직전 이미지가 복구에 필요하므로 수동으로 지우지 마세요.
Docker 이미지·빌드 캐시는 자동 삭제하지 않으므로 디스크 용량은 별도 확인합니다.
status/update는 운영 설정을 임의로 최신 기본값으로 바꾸지 않습니다.

신규 서버 설치 순서는 빌드 → 빈 DB → 승인된 공간 백업 복원 → migration → 히트맵 → 앱 시작입니다.
현재 VM의 `update`는 신규 설치/DB 복원 명령이 아닙니다. head는 0016입니다.
`adopt`/`finalize`는 기존 릴리스 구조를 최초 한 번 전환하는 관리자 명령이며 매 배포마다 실행하지 않습니다.
컨테이너는 running/healthy라도 실제 장소·경로·날씨·마이크까지 자동 검증됐다는 뜻은 아닙니다.
업데이트 후 브라우저에서 확인합니다. GPU endpoint 점검은 LLM live 추론·STT 발화 정확도 평가가 아닙니다.

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

소스 전달본은 `deployment/package.py`가 지정한 출력 경로에 만듭니다.
GitLab 루트의 `SafeAlley-deploy.tar.gz`와 `.sha256`은 교체 가능한 최신 전달본이며,
`output/deployment/`의 커밋명별 파일은 로컬 보관용입니다. 실제 서버 적용 커밋은
현재 VM의 `runtime/state.json`과 보관한 압축본 내부 `release.json`으로 확인합니다.
소스 tar.gz, 비공개 DB dump+체크섬, 서버 비공개 .env를 구분합니다.
tar.gz는 Docker 이미지·공간 DB·원본·모델·비밀값을 포함한 오프라인 설치본이 아닙니다.

```powershell
# uv가 설치된 Windows 개발 PC에서 필요한 경우만. 기존 대상은 덮어쓰지 않습니다.
$releaseCommit = (git rev-parse --short HEAD).Trim()
uv run --python 3.12 --no-project python deployment/package.py --ref HEAD --output "output/deployment/SafeAlley-main-$releaseCommit.tar.gz"
# 검증 후 GitLab 전달본을 교체할 때는 압축본과 .sha256을 함께 갱신합니다.
uv run --python 3.12 --no-project python deployment/manage.py backup --source-local --exclude-feedback --file output/private-transfer/safealley.dump
```

package.py는 커밋된 Git 파일만 포함합니다. 미커밋 변경은 배포되지 않으며
`--ref`로 소스 커밋을 고정합니다. release.json의 base_commit/파일별 체크섬과
아카이브 체크섬을 확인합니다. .env.example과 NOTICE.md는 포함하고 실제 .env·DB·모델은 제외합니다.
추천/선택 기록 제외는 개발 이관용 선택사항이며
정식 운영 전체 백업에서는 --exclude-feedback을 사용하지 않습니다.
DB dump는 암호화되지 않으므로 별도 접근권한/전송 보호가 필요합니다.

현재 VM 갱신은 위 `runtime/update.py update`를 사용합니다. 템플릿 Compose를 현재 VM에
직접 덮어쓰거나 과거 `main-*` 폴더의 명령으로 재생성하지 않습니다.
HTTPS 구성은 소스 Nginx 기본 파일과 별도이며 고정 runtime 설정에 항상 포함됩니다.
저장소의 전달본 커밋과 아카이브 내부 release.json의 소스 base_commit은 구분합니다.

frontend 이미지 빌드는 공개 정적 파일의 권한을 디렉터리 755/파일 644로 정규화합니다.
서버의 제한적인 umask로 추출된 이미지도 Nginx worker가 읽을 수 있어야 합니다.
운영 검증에는 `frontend/tests/welcome-intro.e2e.cjs`도 포함해 첫 안내창의 로고 8개를
실제로 디코딩하는지 확인합니다. `/healthz` 성공만으로 이미지 접근 권한은 검증되지 않습니다.
이 UI 테스트는 소스·브라우저가 준비된 별도 테스트 환경에서 실행합니다. VM status의
진입 JS/CSS 점검은 로고 디코딩·사용자 마이크·실제 길찾기 전체 검증의 대체가 아닙니다.

## 검증·운영

[전체 테스트](../docs/testing.md), [배포 점검](../docs/deployment-checklist.md)을 따릅니다.
소스 테스트 통과는 실제 GPU/음성/포워딩/HTTPS 검증의 대체가 아닙니다.
실제 요청 후 GPU 호스트 ollama ps, 대상 DB·migration·정밀 시설 좌표·타일·날씨를 확인합니다.
proxy는 스트림 buffering off, query 읽기 timeout 660초, 음성 8MB/180초를 유지합니다.
마이크는 localhost 개발 또는 HTTPS에서 사용합니다.

정지/백업/이전 이미지 보관과 복원 연습을 수행합니다. down -v로 볼륨을 지우지 않습니다.
앱 이미지 롤백은 DB migration 롤백이 아니며 기존 운영 DB를 자동 downgrade/교체하지 않습니다.
