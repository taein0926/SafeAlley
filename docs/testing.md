# 현재 서비스 테스트

프로덕션 로직을 테스트 통과 목적으로 우회하지 않는다. 폐기된 기능의 기대값만
정리하고, 라우팅·시설 데이터·좌표·선택 상태·오류 처리 회귀 검증은 유지한다.

## Python

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
공식 원본 ZIP이 없는 테스트와 명시적 환경설정이 필요한 live proxy 테스트의
skip은 통과와 구분해서 보고한다.

배포 스크립트의 격리된 계약 테스트(서버 배포/접속 없음):

```powershell
Push-Location deployment
python -m unittest discover -v
Pop-Location
```

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
