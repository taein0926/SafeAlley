# 현재 서비스 테스트

프로덕션 로직을 테스트 통과 목적으로 우회하지 않는다. 폐기된 기능의 기대값만
정리하고, 라우팅·시설 데이터·좌표·선택 상태·오류 처리 회귀 검증은 유지한다.

## Python

아래 단위·통합·UI 테스트는 소스를 clone한 개발/격리 테스트 환경에서 실행한다.
현재 VM은 `runtime/private/packages` 구조이며 소스 폴더와 tools 프로필을 상시 제공하지 않는다.
VM에서 루트 Compose 예시로 컨테이너를 재생성하거나 운영 DB에 fixture 테스트를 실행하지 않는다.
저장소 루트 PowerShell에서 현재 소스를 읽기 전용으로 테스트 컨테이너에 연결한다.
기존 실행 컨테이너 이미지의 오래된 테스트를 실행하지 않도록 주의한다.

```powershell
docker compose up -d database backend
docker compose run --rm --no-deps -v "${PWD}/backend:/app:ro" backend python -m pytest -p no:cacheprovider -q tests
docker compose run --rm --no-deps --entrypoint python -v "${PWD}/data_pipeline:/pipeline:ro" pipeline -m pytest -p no:cacheprovider -q tests
```

백엔드 통합 테스트는 로컬 PostGIS에 `test-*-fixture` 데이터만 생성하고 종료 후
정리한다. 파이프라인 공간 적재 테스트는 트랜잭션 롤백을 사용한다.
운영 서버 DB를 연결해서 실행하지 않는다.
음성 단위 테스트는 GPU 서비스/VM 대체 분기를 모의 검증하며 실제 GPU 속도나
마이크 정확도를 보장하지 않는다.
공식 원본 ZIP이 없는 테스트와 명시적 환경설정이 필요한 live proxy 테스트의
skip은 통과와 구분해서 보고한다.

배포 스크립트의 격리된 계약 테스트(서버 배포/접속 없음). 아래 Windows 예시는
`uv`가 설치된 환경을 기준으로 하며, 정상 동작하는 Python 3.10+가 있으면 `python -m unittest discover -v`도 가능합니다.

```powershell
Push-Location deployment
uv run --python 3.12 --no-project python -m unittest discover -v
Pop-Location
```

여기에는 `vm_update.py`의 압축 경로·체크섬·manifest 검증, 운영 설정 변경 차단,
빌드 실패 시 서비스 보존, 교체 실패 복구, migration 승인·복구 제한, 임시 소스 제거와
관리 대상 백업 정리 테스트가 포함된다. 중복 배포 차단의 Linux flock 테스트는
Windows에서 skip되며 Linux 격리 환경에서 따로 실행한다.

`tests/unit/test_evaluation_contracts.py`는 전체 자연어 평가셋에 폐기된 경사 선호 정답이
없는지 확인하고, 현재 추천 설명 회귀 사례를 실행한다. 실제 GPU 호출 없이 정답 자료와
설명 함수의 일치 여부를 검사하는 것이며 새로운 모델 정확도 측정은 아니다.

Laya 회귀 테스트는 `tests/unit` 밖의 `tests/test_laya*.py`에도 있으므로 함께 실행합니다.
backend에서 PowerShell로 실행하는 예시는 아래와 같습니다. 실제 DB·유료 API·GPU 호출은 mock입니다.

```powershell
$layaTests = Get-ChildItem tests/test_laya*.py | ForEach-Object FullName
python -m pytest -q tests/unit @layaTests
```
Laya 선택/비활성/모델 해시/응답 형식/입력 버전/부정·철회·미완성·출발 시각과 Jev 기본값 보존을 확인합니다.
실제 GPU `/health`와 `/analyze`, 브라우저 8개 카드 및 최종 Gemma 검색은 별도 live 검증입니다.

## Frontend

Node 22.18 이상 또는 TypeScript strip-types를 지원하는 Node와 `npm ci`가 필요하다.

```powershell
cd frontend
npm test
npm run test:cesium
npm run build
```

## 실제 브라우저 UI

로컬 서비스가 최신 빌드로 실행 중이어야 한다.
테스트 실행 환경에 `playwright`와 Chrome이 필요하다. Playwright는 테스트용이며
서비스 런타임 의존성으로 추가하지 않는다.

```powershell
docker compose build frontend
docker compose up -d --no-deps frontend
cd frontend
npm run test:ui
```

기본 주소는 `http://127.0.0.1:3000/`, 다른 로컬 포트는 `E2E_BASE_URL`로 지정한다.
일반 UI 테스트는 세션 소개창을 건너뛰고 소개창 전용 테스트는 첫 표시·닫기·ESC·
세션 재표시 방지·공식 로고 로딩을 직접 검증한다.
예시 선택 테스트는 네 문장이 중간 문자열 없이 한 번에 입력되는지, 직접 설정에서 문장 입력으로
전환되는지, 자동 검색 없이 즉시 수정 가능한지를 확인한다. 키보드 테스트는 Enter 검색,
Shift+Enter 줄바꿈, 한글 조합 확정·키 반복·빈 입력의 검색 방지를 확인한다.
날씨/요구사항 분석/언어 해석/경로 응답은 명시적인 fixture를 사용하므로 유료
Jev 호출, 실제 LLM 추론, 추천 이력 DB 쓰기는 수행하지 않는다. 이는 UI 회귀
검증이며 AI 모델 정확도나 실제 경로 품질의 live 검증을 대체하지 않는다.
지도와 가로등 밀집도 타일은 실행 중인 로컬 서비스의 실제 자산을 읽는다.

## 배포 후 연결 확인

VM에서는 먼저 아래 읽기/연결 검사를 실행한다. update 명령은 새 배포본을 실제로 적용할 때만 사용한다.

```bash
python3 ~/safealley-deploy/runtime/update.py status
docker compose -p safealley-deploy -f ~/safealley-deploy/runtime/compose.json ps
```

status는 네 컨테이너의 상태·고정 설정 경로·이미지, HTTPS 인증서 검증·HTTP 이동,
프론트 JS/CSS·DB health와 GPU Ollama 모델 목록·Whisper CUDA ready endpoint를 확인한다.
날씨 값·지도 전체 데이터·실제 LLM 추론·음성 전사 정확도를 검사하는 명령은 아니다.
backend/frontend의 healthy 상태와 `/api/health`, 지도 타일을 확인한다.
backend의 실제 `OLLAMA_MODEL`과 적용된 `OLLAMA_BASE_URL`의 Ollama 응답을 대조한다.
저장소 VM override의 모델 기본값은 실제 비공개 서버 설정을 증명하지 않는다.

승인된 HTTPS 또는 localhost 접속에서 짧은 음성을 직접 녹음하고 브라우저 개발자 도구의
`/api/speech/transcribe` 응답에서 `model=small`, `device=cuda`, 인식 텍스트를 확인한다.
`device=cpu`라면 GPU 처리 성공으로 보고하지 말고 적용된 `STT_REMOTE_URL` 연결과 GPU 서비스 상태를 확인한다.
GPU 연결 실패 시 CPU 대체는 운영 터널을 일부러 중단하지 말고 격리된 테스트 환경에서 확인한다.
응답의 `latency_ms`는 디코딩·추론 내부 시간이고 브라우저↔VM↔GPU 전체 왕복 시간은 아니다.
실제 모델 호출·마이크·공간 경로 확인은 mock 테스트와 구분해서 보고한다.

VM 이미지 정리는 `runtime/update.py clean-images --dry-run`으로 대상을 먼저 확인한다.
업데이터 안전 테스트에는 현재·직전 복구 이미지, 중지된 컨테이너, Workhub 등 다른 프로젝트의
태그·digest 공유 보호, 삭제 직전 재조회, 태그 변경·Docker 오류 시 중단 검사가 포함된다.
전체 이미지/빌드 캐시 prune과 강제 삭제는 하지 않으며, 실제 정리 후에는 보호 참조·컨테이너
동일성 및 HTTPS·GPU endpoint를 재확인한다. 이는 실제 롤백 실행이나 DB 복원 시험은 아니다.
이미지 이름 규칙은 한국 시간 변환·날짜 경계·커밋 형식·기존 태그 덮어쓰기 차단 및
`safealley-release/database` 보존을 테스트한다. DB는 앱 이미지 태그 생성/재빌드 대상에서 제외한다.
실행 템플릿의 모델 기본값 일치, OSM의 비데모 기본값, 건물 CLI의 MOLIT 기본 출처와 명시적
출처 유지도 회귀 검사한다. 건물 source 불일치 검사는 모의 DB 연결로 실제 접속 전에 중단됨을 확인한다.
