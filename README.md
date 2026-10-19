# 안전골목길 · SafeAlley

골목에 안전을 더하다.

인천 미추홀구 도로·건물·시설 공간정보로 보행 경로를 비교하는 서비스입니다.
문장으로 이동 조건을 요청하거나 출발·도착지와 경로 기준을 직접 설정합니다.
시설 등록 위치 기반 추천이며 실제 밝기·시설 운영·현장 통행 안전을 보장하지 않습니다.

## 주요 기능

- 문장 입력: Ollama가 장소·시간·선호조건을 추출하고 backend가 경로를 계산합니다.
- 직접 설정: 장소명 또는 지도 선택 좌표, 경로 우선순위·계단 회피·건널목 회피를 사용합니다.
- 요구사항 미리보기: 선택적 Jev 연동으로 입력 중 인식된 조건을 표시합니다. 최종 경로 판정과는 별개입니다.
- 경로 비교: 맞춤·최단 후보의 거리·예상 시간·계단·육교·횡단보도 정보를 표시하고 동일 경로는 중복 제거합니다.
- 지도: OSM 배경지도, 건물 3D 표현, 시설·계단/육교 토글, 유지되는 2D/3D 시점.
- 날씨: 미추홀구 대표 격자 예보와 당일 일출·일몰 캐시.
- 음성 입력: VM에서는 GPU 서버의 Whisper `small`로 우선 변환하고, 연결 실패 시 backend CPU로 대체합니다. 자동으로 길찾기를 실행하지 않습니다.
- 소개창: 세션 첫 접속에 표시하며 닫기·ESC·바깥 클릭을 지원합니다.

## 구성

```text
브라우저 ── 직접 타일 요청 ── OSM Tile Server
   └─ React / CesiumJS (Nginx)
        └─ /api/* → FastAPI → PostgreSQL / PostGIS
                       ├─ Ollama: 문장 해석(GPU 서버 터널)
                       ├─ Whisper: 음성 변환(GPU 서버 우선·backend CPU 대체)
                       ├─ Jev: 선택적 입력 중 조건 해석
                       └─ Nominatim: 장소 검색 fallback

data_pipeline: 외부 원본 → 수집 → 정제 → 좌표 변환 → PostGIS
weather 배치: 발표 시각별 예보 / 당일 일출·일몰 → DB 캐시
```

Frontend는 DB에 직접 접근하지 않습니다. `/api`는 HTTP 경로이고 실제 처리 서버가 FastAPI입니다.
DB 공간 연산은 EPSG:5179(m), API/GeoJSON은 EPSG:4326(경도·위도)을 사용합니다.

## 로컬 실행

Docker Desktop(Windows는 Linux 컨테이너) 또는 Docker Engine과 Compose v2가 필요합니다.
저장소 루트에서 실행합니다.

```powershell
# 최초 한 번만 복사. 기존 .env는 덮어쓰지 마세요.
Copy-Item .env.example .env
# .env의 DB 비밀번호와 필요한 연동 설정을 편집한 뒤 실행
docker compose up -d --build
```

- 서비스: http://localhost:3000
- 실제 DB/PostGIS 연결 확인: http://localhost:8000/health
- API 명세: http://localhost:8000/docs
- 종료: `docker compose down` — 데이터 볼륨은 유지합니다.

기본 컨테이너는 frontend/backend/database/weather입니다.
pipeline은 tools 프로필의 일회성 명령이며 웹 서버가 아닙니다.
Backend 시작 시 Alembic migration을 적용하고 현재 저장소 head는 0016입니다.

**Git clone과 컨테이너 시작만으로 기존 공간 데이터가 복원되지는 않습니다.**
도로·건물·시설·장소, raw/processed 원본, 히트맵 타일은 별도 적재/승인된 백업 이관이 필요합니다.
빈 DB에서는 데이터 기반 검색을 할 수 없습니다.
기존 서비스 DB에서 OSM 재적재 명령을 무심코 실행하지 말고 [데이터 운영](docs/data-pipeline.md)을 확인하세요.

## 환경변수와 모델

실제 비밀값은 .env에서만 관리하고 커밋하지 않습니다. VITE_*는 공개되는 빌드 설정입니다.

| 기능 | 설정 | 기본/주의 |
| --- | --- | --- |
| DB | POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD | 기존 볼륨 계정은 .env 변경만으로 바뀌지 않음 |
| 문장 해석 | OLLAMA_BASE_URL / OLLAMA_MODEL | 로컬 host.docker.internal:11434 / gemma4:26b, API 키 불필요 |
| 요구사항 미리보기 | JEV_PREVIEW_ENABLED / TYPESAFE_API_KEY | 기본 false, 별도 유료 Jev 기능 |
| 날씨 | KMA_SERVICE_KEY / KASI_SERVICE_KEY | 서비스별 공공데이터포털 승인 키 |
| 장소 fallback | NOMINATIM_BASE_URL / NOMINATIM_USER_AGENT | 지역 제한·캐시·요청 간격 적용 |
| 음성 | STT_MODEL / STT_REMOTE_URL | `small`; 원격 주소가 있으면 GPU 우선, 연결 실패 시 CPU INT8·stt_models 볼륨 캐시 |
| 지도 | VITE_OSM_TILE_URL / VITE_BUILDING_SOURCE | OSM 타일 / molit-gis-building |

Windows 호스트 Ollama를 사용하는 **기본 로컬 설정**(모델을 실행할 충분한 GPU 자원이 필요합니다):

```powershell
ollama --version
ollama pull gemma4:26b
ollama serve # 이미 실행 중이면 새로 실행하지 않습니다.
Invoke-RestMethod http://localhost:11434/api/tags
docker compose up -d --force-recreate backend
```

다른 모델/서버를 사용하면 .env를 실제 설치에 맞게 설정합니다.
VM/GPU 분리 구성의 실제 모델·터널 주소는 로컬 기본값과 다를 수 있습니다.
적용된 서버 설정과 템플릿의 차이는 [배포 안내](deployment/README.md)에서 확인하세요.
환경변수 변경은 컨테이너 재생성, VITE_* 변경은 frontend 재빌드가 필요합니다.

## 검색·데이터 원칙

장소 문자열은 places(정규화·별칭·부분 검색) → 지역 제한 GIS 건물 → Nominatim fallback으로
해석하고 외부 결과는 장소 DB에 재사용합니다. 문장 입력과 직접 설정은 같은 resolver를 사용합니다.
지도 선택 좌표는 문자열 검색을 다시 거치지 않고, 입력 수정 시 이전 좌표를 무효화합니다.

최단·맞춤 모두 연결된 인도/보행로를 우선하는 정책을 사용합니다.
그 기준에서 최단은 거리, 맞춤은 요청한 시설·계단·건널목 비용을 반영합니다.
허용된 일반 도로도 연결을 보완하지만 실제 보행 안전을 인증하지 않습니다.
인위적인 우회로 차이를 연출하지 않습니다. [라우팅 상세](docs/routing.md)를 참고하세요.

OSM 도로/계단/건널목, 공식 MOLIT 건물 SHP, 가로등 위치, 정밀 CCTV 및 경찰·119·병원
GeoJSON을 사용합니다. 건물은 i-Map에서 무단 수집한 파일이 아닙니다.
유동인구는 실제 연동되지 않았으며 전체 안전도 도로선·도로 검사 오버레이는 현재 화면에 표시하지 않습니다.
원천·라이선스는 [NOTICE.md](NOTICE.md)에 기록합니다.

## 주요 API

| API | 역할 |
| --- | --- |
| GET /health | DB/PostGIS 연결 확인 |
| GET /api/roads?source=osm | 도로·계단 metadata GeoJSON |
| GET /api/safety/roads | 분석 구간 조회 |
| GET /api/buildings, /api/streetlights, /api/cctvs, /api/help-points | bbox 지도 객체 |
| GET /api/pedestrian-bridges | 육교 참조 |
| GET /api/places/resolve, /api/places/reverse | 장소명·지도 좌표의 표시명 |
| POST /api/agent/query/stream | 문장 해석 → 장소 확인 → 경로 진행 → 결과(NDJSON) |
| POST /api/agent/execute | 직접 설정의 검증된 rank_routes 실행 |
| POST /api/routes/shortest, /api/routes/safe | 좌표 경로 GeoJSON |
| POST /api/agent/route-selections | 후보 선택 기록 |
| GET /api/agent/intent-preview/status, POST /api/agent/intent-preview | Jev 상태·미리보기 |
| GET /api/weather?departure_time=22:00 | DB의 해당 시간 예보 |
| POST /api/speech/transcribe | 음성 → 텍스트 |
| GET /api/streetlight-heatmap/manifest | 표시용 밀집도 타일 |

정확한 필드 정본은 FastAPI /docs와 backend/app/schemas입니다.
표시 전용 /api/osm-roads, /api/crossings는 제거됐습니다.

## 디렉터리

```text
frontend/        React UI, Cesium·캐시, 단위/브라우저 테스트
backend/app/     api / schemas / services / repositories / db
backend/alembic/ DB migration 이력
backend/tests/   단위·PostGIS 통합 테스트
data_pipeline/   collectors / preprocess / loaders / analysis, 배치·테스트
database/        PostGIS extension 초기화
deployment/      서버 패키징·Compose·안전 계약 테스트
docs/            기능·데이터·운영 문서
output/          로컬 검증 산출물(Git 제외)
```

## 문서와 검증

배포 소스 전달본은 `deployment/package.py`로 커밋을 고정해 생성합니다. GitLab 루트의 `SafeAlley-deploy.tar.gz`와 `.sha256`은 최신 전달본으로 교체하며, `output/deployment/`는 로컬 보관용입니다.
실제 서버 적용 커밋은 서버 릴리스의 `release.json`으로 확인합니다. 문서 수정은 새 커밋과 새 묶음을 만들기 전까지 기존 전달본에 반영되지 않습니다.
실제 .env·DB·모델은 포함하지 않으며, 아카이브 내부 release.json으로 소스 커밋과 파일 체크섬을 확인합니다.
기존 VM 업데이트에서는 데이터·비공개 설정·GPU 모델을 보존합니다. [배포 절차](deployment/README.md)

- [테스트 실행](docs/testing.md)
- [아키텍처](docs/architecture.md) · [DB](docs/database-schema.md) · [라우팅](docs/routing.md)
- [데이터 구축](docs/data-pipeline.md) · [건물 원천/매핑](docs/building-data.md)
- [날씨](docs/weather.md) · [음성](docs/speech-input.md) · [소개창](docs/welcome-intro.md)
- [검색 진행·후보 카드](docs/route-progress-floating-cards.md)
- [배포](deployment/README.md) · [점검](docs/deployment-checklist.md)
- [문장 해석](docs/natural-language.md) · [AI 연결](docs/ai-setup.md) · [전체 문서](docs/README.md)

Mock/합성 테스트는 실제 모델 정확도·시설 운영·현장 안전의 live 검증이 아닙니다.
수정 시 [AGENTS.md](AGENTS.md)를 따릅니다.
