# Ollama 연결과 복구

Ollama가 문장을 해석하고 FastAPI가 장소·경로를 처리합니다.
현재 모델·주소는 비공개 .env와 적용한 Compose 조합이 정본입니다.
이 문서만으로 로컬/서버 설치·실행 여부를 단정하지 않습니다.

## Windows 로컬 기본

.env.example: OLLAMA_BASE_URL=http://host.docker.internal:11434, OLLAMA_MODEL=gemma4:26b.
이 모델을 PC에서 직접 실행하려면 충분한 GPU 자원이 필요합니다. 기존 GPU 서버를 사용하는 로컬 설정은 아래 터널 절차를 따릅니다.

```powershell
ollama --version
ollama pull gemma4:26b
ollama serve # 이미 실행 중이면 생략
Invoke-RestMethod http://localhost:11434/api/tags
docker compose up -d --force-recreate backend
docker compose exec backend python -c "import os,urllib.request; print(urllib.request.urlopen(os.environ['OLLAMA_BASE_URL']+'/api/tags', timeout=10).status)"
```

## VM/GPU 또는 GPU 터널

승인된 터널은 GPU Ollama loopback 11434를 host gateway 11435로 전달합니다.
VM override의 기본 모델은 qwen3.6:35b입니다.
Windows 로컬에서도 GPU를 사용하려면 실제 승인된 터널 주소/포트와 모델에 맞게 .env를 설정합니다.
단일 GPU Compose 대안은 http://ollama:11434를 사용하므로 VM 터널 설정과 다릅니다.

GPU 호스트의 ollama list/ps, VM/PC 터널의 수신 포트·지문·접속 권한을 확인합니다.
터널 창 종료·절전·재부팅 후 복구 방식은 서버 운영 정책을 따릅니다.
GPU 공용 Ollama를 임의로 재시작하거나 기존 모델을 제거하지 않습니다.
비밀번호/개인키는 문서·소스에 기록하지 않습니다.

## 로컬 앱에서 기존 GPU Gemma 사용

2026-10-13 로컬 연결 확인 모델은 `gemma4:26b`입니다. 모델은 PC가 아니라 기존 GPU 서버에서 실행합니다.
별도 PowerShell 창에서 아래 터널을 열고 창을 유지합니다. SSH 인증은 기존 계정으로 진행하며 비밀번호를 파일에 저장하지 않습니다.

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes -p 19922 -L 127.0.0.1:11435:127.0.0.1:11434 ltmetric@211.58.157.60
```

루트 `.env` 설정(커밋하지 않음):

```dotenv
OLLAMA_BASE_URL=http://host.docker.internal:11435
OLLAMA_MODEL=gemma4:26b
```

```powershell
Invoke-RestMethod http://127.0.0.1:11435/api/tags
docker compose up -d --no-deps --force-recreate backend
docker compose exec backend python -c "import os,json,urllib.request; print(os.environ['OLLAMA_MODEL']); print(json.load(urllib.request.urlopen(os.environ['OLLAMA_BASE_URL']+'/api/tags', timeout=10)))"
```

브라우저 `http://localhost:3000/`의 길찾기 요청은 로컬 FastAPI가 처리하고, 문장 해석만 SSH 터널로 GPU Ollama에 전달합니다.
DB/경로 탐색은 로컬에 남고 Jev 미리보기 설정은 바뀌지 않습니다. 터널 종료·PC 재시작 후에는 다시 연결해야 하며 자동 시작은 설정하지 않습니다.
`docker compose restart`만으로는 새 `.env` 값이 반영되지 않으므로 위 재생성 명령을 사용합니다.

## 직접 API 확인

아래 요청은 실제 추론/경로 계산을 실행합니다. 데이터가 있어야 하며 대기시간이 필요할 수 있습니다.

```powershell
$payload = @{query='밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘'} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/agent/query -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
```

연결 실패는 endpoint/터널/모델 준비·자원·timeout을 순서대로 확인합니다.
형식/의미 실패와 연결 실패를 구분하고 다른 모델로 자동 전환하지 않습니다.
의도 캐시를 끄거나 새 문장으로 실제 모델 호출 여부를 확인하고 준비/초기 적재 시간을 구분해 측정합니다.

TYPESAFE_API_KEY는 Ollama 키가 아니라 별도 Jev 미리보기 키입니다.
KMA/KASI 키도 서로 다른 서비스입니다. 키를 VITE_*로 노출하지 않습니다.
[배포 구성](../deployment/README.md), [해석](natural-language.md), [캐시](ai-search-performance.md).
