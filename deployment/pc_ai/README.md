# PC의 Gemma·Whisper·Laya를 함께 사용하는 구성

로컬 웹과 VM 웹은 같은 PC 모델을 사용한다. FastAPI의 경로 계산과 DB 접근은 각 서버에 남는다.
외부 GPU 서버 `211.58.157.60`은 이 구성에서 사용하지 않는다.

| 기능 | PC 실행 위치 | VM backend의 연결 주소 |
|---|---|---|
| 자연어 길찾기 | Ollama `gemma4:e2b-it-qat`, GPU, context 4096 | `http://host.docker.internal:11439` |
| 음성 입력 | `pc-whisper`, small, CPU INT8, 2스레드 | `http://host.docker.internal:11440` |
| 조건 카드 | `pc-laya`, 검증한 ONNX FP32, CPU 2스레드 | `http://host.docker.internal:18763` |

Whisper와 Laya는 PC CPU에서 실행하여 Gemma 및 기존 다른 프로그램의 GPU 메모리와 경쟁하지 않는다.
Laya 체크포인트 SHA-256은 `b3522f4d79391a93d9272bccdd3a8aadec601b11e9a2be3ea248eb58dd49a9da`다.
모델·DB·비공개 설정은 Git과 배포 압축파일에 포함되지 않는다. Git 복제만으로 모델이 복원되지는 않는다.

## PC 준비 및 기동

Docker Desktop, Ollama, Windows OpenSSH가 필요하다. Ollama에는 위 Gemma 모델이 있어야 한다.
검증한 `safealley-laya-onnx-cpu:b3522f4d7939-v1` 이미지와 Laya 실행 폴더,
기존 `safealley_stt_models` 볼륨의 Whisper 캐시를 보존한다.
Laya 실행 폴더에는 `laya-fp32.onnx`, `onnx-model.json`, `checkpoint-meta/`가 필요하다.
다른 PC로 복구할 때는 이 파일과 Docker 이미지/볼륨도 함께 이동해야 한다.

루트의 비공개 `.env`에 다음 항목을 설정한다. DB와 지도 설정은 기존 값을 유지한다.

```dotenv
COMPOSE_FILE=docker-compose.yml;deployment/compose.pc-ai.yml
COMPOSE_PATH_SEPARATOR=;
LAYA_RUNTIME_DIR=C:/절대경로/검증한-Laya-실행폴더
```

`deployment/.private/pc-ai/connection.json`에 `host`, `port`, `user`, `key`를 저장한다.
`key`는 현재 Windows 사용자만 읽을 수 있는 SSH 개인키의 절대 경로다.
키와 비공개 설정을 커밋하지 않는다. VM의 호스트 키는 별도 신뢰 경로로 확인 후 known_hosts에 등록한다.
전용 공개키는 셸 실행을 막고 loopback 역방향 포트 `21434`, `28081`, `28761`만 허용한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/pc_ai/start.ps1
```

기본 실행은 로컬 서비스와 모델만 준비하며 VM에는 연결하지 않는다.
사용자가 VM 연결을 요청했을 때만 다음 명령을 실행한다. 로그인 자동 연결은 등록하지 않는다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/pc_ai/start.ps1 -ConnectVm -TunnelOnly
```

`-ConnectVm`은 VM 연결을 명시적으로 요청하는 옵션이고 `-TunnelOnly`는 모델 기동을 생략한다.
연결 관리자가 실행되는 동안에는 SSH 종료 시 재시도한다. 중복 연결은 mutex로 방지한다.
PC 종료·절전·로그아웃 또는 인터넷 단절 중에는 AI 기능을 제공할 수 없다.
노트북 절전 설정은 사용자가 운영 조건에 맞게 관리한다.

## VM 연결과 배포

VM의 `/home/ltmetric/safealley-pc-ai/compose.json`은 작은 TCP 전달기만 실행한다.
`relay.py`는 Docker 전용 호스트 주소에만 바인딩하고 지정한 앱 네트워크 CIDR만 허용한다.
인터넷에 모델 API를 공개하지 않는다. SSH는 VM loopback 포트를 PC loopback 포트로 연결한다.
Docker 네트워크 주소가 바뀌면 전달기의 `--bind`, `--allow`를 실제 주소로 갱신한다.

VM의 비공개 `backend.env`에서 위 세 주소와 다음 설정을 사용한다.

```dotenv
OLLAMA_MODEL=gemma4:e2b-it-qat
OLLAMA_KEEP_ALIVE=-1m
STT_LOCAL_FALLBACK=false
INTENT_PREVIEW_PROVIDER=laya
LAYA_PREVIEW_ENABLED=true
LAYA_CHECKPOINT_SHA256=b3522f4d79391a93d9272bccdd3a8aadec601b11e9a2be3ea248eb58dd49a9da
JEV_PREVIEW_ENABLED=false
```

VM backend의 Whisper 모델 볼륨 마운트와 기존 Laya 실행기는 전환 검증 후 제거한다.
`safealley-ollama-tunnel`, `safealley-stt-tunnel`, `safealley-laya-tunnel`만 정리 대상으로 삼는다.
다른 서비스가 사용하는 `gpu-ollama-tunnel`과 DB·지도·날씨 데이터는 보존한다.
VM 앱 배포는 기존 `safealley-deploy/runtime/update.py` 절차를 사용하며 DB 백업과 롤백을 유지한다.

## 확인 방법

`docker compose ps`, `ollama ps`와 비공개 `tunnel-manager.log`를 확인한다.
PC의 `127.0.0.1:18081/health`, `127.0.0.1:18761/health`가 준비 상태여야 한다.
VM backend 안에서 세 모델 주소의 `/api/tags` 또는 `/health`가 응답해야 한다.
웹에서 음성 입력 후 텍스트, 입력 중 조건 카드, 최종 자연어 경로를 각각 확인한다.
`STT_LOCAL_FALLBACK=false`는 PC가 끊어졌을 때 VM CPU에 모델을 내려받거나 실행하지 않도록 한다.
