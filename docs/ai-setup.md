# PC 모델 연결과 복구

현재 로컬·VM은 PC의 Ollama `gemma4:e2b-it-qat`(GPU), Whisper `small`(CPU INT8),
Laya ONNX FP32(CPU)를 함께 사용합니다. FastAPI의 장소·경로 처리와 DB는 각 앱 서버에 남습니다.
설치된 모델·주소는 로컬 비공개 `.env`와 PC AI override, VM의 `private/service-env/backend.env`가 정본입니다.

## PC 준비와 로컬 실행

Docker Desktop, Ollama, Windows OpenSSH를 준비합니다. Ollama 앱을 실행한 뒤 Gemma 모델을 준비합니다.
직접 서버를 실행한다면 별도 PowerShell 창에서 `ollama serve`를 실행해 유지합니다.
아래 명령은 원래 창에서 실행하며 이미 실행 중인 Ollama를 다시 기동하지 않습니다.

```powershell
ollama pull gemma4:e2b-it-qat
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Gemma 외에 검증한 Laya 이미지·ONNX/메타데이터·Whisper 모델 캐시를 별도로 준비해야 합니다.
[PC AI 운영 안내](../deployment/pc_ai/README.md)의 `.env` 설정 후 저장소 루트에서 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/pc_ai/start.ps1
```

이 명령은 로컬 서비스와 모델을 준비하며 VM에 연결하지 않습니다.
일반 `.env.example`과 기본 Compose의 `gemma4:26b`는 이전 설치용 기본값입니다.
현재 PC 구성은 `deployment/compose.pc-ai.yml`이 모델·provider·음성 설정을 덮어씁니다.
backend를 별도로 재생성할 때도 같은 Compose 조합과 프로젝트를 유지합니다.

## VM에 PC 모델 연결

비공개 `deployment/.private/pc-ai/connection.json`의 `host`, `port`, `user`, `key`와
확인한 SSH 서버 지문이 필요합니다. 전용 키는 모델용 역방향 포트만 허용하며 관리자 SSH와 구분합니다.
PC 모델을 먼저 준비한 뒤 별도 PowerShell 창에서 실행하고 창을 유지합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deployment/pc_ai/start.ps1 -ConnectVm -TunnelOnly
```

| 기능 | 로컬 backend 주소 | VM backend 주소 |
| --- | --- | --- |
| Gemma E2B | http://host.docker.internal:11434 | http://host.docker.internal:11439 |
| Whisper small | http://pc-whisper:18081 | http://host.docker.internal:11440 |
| Laya ONNX | http://pc-laya:18761 | http://host.docker.internal:18763 |

VM 전달기는 앱 네트워크에서만 접근하도록 바인딩·CIDR를 제한합니다.
PC 종료·절전·로그아웃·네트워크 단절 시 AI 기능을 사용할 수 없습니다.
`STT_LOCAL_FALLBACK=false`이므로 VM에서 음성 모델을 대신 실행하지 않습니다.
연결 관리자는 실행 중 재연결하며 로그인 자동 연결은 등록하지 않습니다.
VM 웹·관리자 SSH·소스 업데이트는 [배포 안내](../deployment/README.md)를 따릅니다.

## 상태 확인과 장애 대응

PC에서 `docker compose ps`, `ollama ps`, `127.0.0.1:18081/health`,
`127.0.0.1:18761/health`와 비공개 `tunnel-manager.log`를 확인합니다.
VM은 `python3 ~/safealley-deploy/runtime/update.py status`로 적용 소스·앱·연결 상태를 확인합니다.
VM backend에서 위 세 주소의 `/api/tags` 또는 `/health`가 응답해야 합니다.

Laya는 `/api/agent/intent-preview/status`의 enabled/configured/available과 실제 8개 카드 판정을 함께 확인합니다.
화면은 미준비·연결 오류 뒤 5초 간격으로 상태를 재확인하고, 준비되면 현재 입력을 분석합니다.
모델 health 성공만으로 문장 해석·경로·음성 정확도를 검증한 것은 아닙니다.

장애는 PC 기동·모델 준비 → PC health → SSH 지문/키/터널 → VM 전달기 → backend 설정 순서로 확인합니다.
Laya·Jev·다른 Gemma 모델로 자동 전환하지 않습니다. 환경변수 변경은 컨테이너 재생성이 필요합니다.
기존 GPU 서버의 모델·다른 프로젝트 서비스·DB·인증서는 변경하지 않습니다.

TYPESAFE_API_KEY는 선택형 Jev 키이며 Ollama 키가 아닙니다. KMA/KASI도 별도 서비스 키입니다.
키는 `VITE_*`나 Git에 넣지 않습니다. [Laya 계약](laya-preview-provider.md),
[음성 입력](speech-input.md), [공개 저장소 점검](public-repository-security.md)을 참고합니다.
