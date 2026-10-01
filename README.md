# SafeAlley

사내 서버 이전 시 [배포 준비 체크리스트](docs/deployment-checklist.md)를 먼저 확인합니다.
소스 push만으로 공간 데이터·Ollama·인증/HTTPS 설정이 배포되지는 않습니다.

## 지도 테마 및 로딩

### 화면 주변 시설 캐시 / 사전 계산 가로등 히트맵

- 가로등·CCTV·안전시설·계단·육교·횡단보도는 화면 주변 bbox만 조회합니다. 20% 여유 영역(최소 0.001도)을 0.01도 타일로 캐시하고, 이동이 끝난 뒤 새 타일만 요청합니다. 꺼진 시설은 조회하지 않습니다. 데이터 캐시는 페이지를 닫으면 사라지며, 화면 밖 지도 객체는 해제합니다. 캐시는 레이어별 96타일을 기준으로 오래된 화면 밖 타일부터 정리합니다(현재 화면 타일은 유지).
- 시설·건물·도로는 독립적으로 표시합니다. 낮에 꺼진 가로등은 조회하지 않으며, 야간 히트맵은 첫 화면 시설 표시 뒤 불러옵니다. 느린 선택 레이어가 있으면 최대 2초 대기 후 히트맵 로딩을 진행합니다.
- 지도 이동 중에는 렌더링 배율을 1.25에서 1.0으로 낮추고 건물 외곽선만 생략하며, 이동 종료 200ms 후 복원합니다. 건물 본체와 캐시 데이터는 유지합니다. 해상도 변경 시 카메라 투영을 보존하고 프레임을 그리기 전에 크기를 조정해 건물 요청 취소 및 검은 화면 깜빡임을 방지합니다.
- 히트맵은 브라우저에서 계산하지 않습니다. `data_pipeline/analysis/streetlight_heatmap.py`가 DB의 가로등 좌표로 45m 반경 밀도 PNG 타일을 생성합니다. 실제 조도·점등 상태가 아닌 위치 기반 시각화입니다. 경로 안전도 계산에는 영향을 주지 않습니다.
- 타일은 Docker `safealley_map_tiles` 볼륨에 영구 저장하고 backend가 읽기 전용으로 제공합니다. 데이터/렌더러 버전별 URL은 브라우저 장기 캐시를 사용합니다. **새 설치 및 가로등 데이터/표현 방식 변경 후 아래 명령을 한 번 실행**합니다. 같은 데이터로 재실행하면 기존 결과를 재사용합니다. 타일 생성이 실패해도 이전 공개 버전은 보존합니다.

```bash
docker compose build pipeline backend frontend
docker compose run --rm --no-deps --entrypoint python pipeline -m analysis.streetlight_heatmap
docker compose up -d --no-deps backend frontend
```

DB는 먼저 실행되어 있고 가로등 데이터가 적재되어 있어야 합니다. 생성 여부는 `/api/streetlight-heatmap/manifest`에서 확인합니다. 타일을 생성하지 않은 서버에서는 히트맵만 표시되지 않으며 지도·시설·검색은 그대로 동작합니다. 회사 서버용 별도 Compose에도 pipeline의 `/map-tiles` 쓰기 볼륨과 backend의 동일 경로 읽기 볼륨 연결이 필요합니다.

### 지도 표시와 검색

- 안전도·계단 회피·건널목 회피는 **낮음 / 중간 / 높음** 세 단계로 설정합니다. 최단·맞춤 경로 모두 연결된 인도·보행로 등 우선 보행망 바깥을 걷는 거리를 먼저 최소화합니다. 그 조건 안에서 최단 경로는 거리를, 맞춤 경로는 요청한 안전시설·계단·건널목 조건을 탐색 비용에 반영합니다. 따라서 표시되는 최단 경로는 일반 도로까지 포함한 무조건적인 최단 거리가 아닙니다.
- 기본 지도 밝기는 낮 1.0, 밤 0.5입니다. 낮에는 가로등 표시를 기본으로 끄고, 밤에는 사전 계산된 밀도 히트맵을 표시합니다. 실제 조도·점등 상태를 나타내지는 않습니다.

- 직접/AI 검색의 **건널목 회피**는 미추홀구 전체에 수집한 OSM 인도·건널목 정보를 사용합니다. 기존 보행 가능한 일반 도로를 유지하되 연결된 인도를 우선합니다. 건널목 회피에 따른 추가 우회는 같은 보행 우선 기준의 기본 경로에서 제한하며, 인도 우선 자체의 우회 상한은 아닙니다. 화면의 횡단보도 수는 OSM 등록 정보 기준으로 실제 모든 횡단을 보장하지 않습니다. 이전 교차로 대표점 반경 비용은 새 검색에서 제외합니다.

- 코드 업데이트만으로 OSM 데이터가 갱신되지는 않습니다. 2026-10-01 공간 ZIP은 Alembic `0015`, 도로 15,694개 기준입니다. 당일 갱신 DB는 `0016`, 도로 16,587개·도로 안전도 구간 36,360개·`public_crosswalks` 98개·표시 전용 `osm_display_roads` 3,741개입니다. 동일한 결과가 필요하면 갱신된 공간 데이터를 별도로 이관하거나 같은 원본 스냅샷과 설정으로 `loaders.osm_refresh` 및 `loaders.osm_display`를 실행해야 합니다. `0016`은 표시 테이블 구조만 만들며 데이터는 채우지 않습니다. 원본 스냅샷·DB 백업·히트맵 타일은 Git에 포함하지 않습니다.

- 직접 검색의 경로 기준에서 출발 시간을 설정합니다. 기본값은 페이지를 연 시점의 브라우저 현지 시각이며, '현재 시간' 버튼으로 갱신할 수 있습니다. 시간을 편집하는 동안은 기존 지도 테마를 유지하고, '경로 검색'을 누르면 해당 시간을 테마와 경로 추천 API에 적용합니다. 탭 전환만으로는 테마가 바뀌지 않습니다. 적용한 출발 시간이 20:00 이상 또는 06:00 미만이면 야간 테마를 표시합니다. AI 검색은 응답에서 해석한 시간으로 테마를 적용하며, 시간이 없으면 주간 테마를 사용합니다.
- 도로 분석 데이터는 동네 수준으로 확대했을 때 화면 주변 bbox만 조회합니다. 카메라 이동 후 250ms 대기, 여유 범위 재사용, 이전 요청 취소로 불필요한 로딩을 줄입니다. 경로 결과가 있으면 추가 도로 분석 조회를 생략합니다.
- 초기 지도는 기존 장소 데이터의 주안역(126.6804, 37.4649)을 중심으로 카메라 고도 1,400m에서 시작합니다. 레이어 로딩 후에는 사용자가 이동한 화면을 초기화하지 않습니다. 전체 안전도 도로선은 숨기고, 숨겨진 도로의 Cesium 객체는 생성하지 않습니다. 화면의 도로 수는 전체 DB 개수가 아닌 마지막 화면 주변 조회 개수입니다.
- 시설 표시 토글은 화면 맨 오른쪽 전용 영역에 고정하며, 경로 결과 및 지도 객체 정보 패널은 그 왼쪽에 표시합니다.
- 건물은 `/api/buildings`의 bbox로 화면 주변만 조회합니다. 화면 가로 0.022도·세로 0.016도 이하에서 20% 여유 범위를 0.004도 고정 구역으로 나누어 캐시합니다. 이미 받은 구역은 재조회하지 않고, 새 구역만 인접한 사각 범위로 묶어 조회합니다. 경계에 걸친 건물은 ID로 중복 생성을 막고 기존 Cesium 객체를 재사용합니다. 이동 종료/화면 크기 변경 후 250ms 대기하며, 이전 요청 취소 및 결과 유효성 검사로 오래된 응답이 지도를 덮어쓰지 않도록 합니다.
- 건물 레이어는 시설·검색 준비와 독립적으로 로딩합니다. 화면 밖 건물은 숨기되 캐시에 유지하고, 축소 후 돌아와도 재사용합니다. 메모리 증가를 막기 위해 64개 구역을 넘으면 오래 사용하지 않은 화면 밖 구역부터 해제합니다(현재 화면 구역은 유지). 건물 속성 및 지도에서 출발지·도착지 선택 기능은 유지하며 원본 DB는 변경하지 않습니다. 데이터 상태에는 현재 표시 수와 캐시 수를 구분합니다.
- 계단은 `/api/roads?source=osm&steps_only=true`로 실제 OSM 계단 구간만 조회하여 중간 위치에 계단 모양 아이콘을 표시합니다. 이모지 글꼴 지원과 무관하게 표시되는 SVG를 사용합니다. 클릭하면 계단 속성을 확인할 수 있습니다. OSM 수록 위치이며 현장 확인이 필요합니다.
- 경로 결과는 내부 탐색용 '총 비용' 대신 도보 4.5km/h(분당 75m) 기준의 예상 소요 시간을 올림하여 표시합니다. 신호 대기·계단 지연·개인 보행속도는 반영하지 않으며, API의 비용 계산과 경로 순위는 그대로 유지합니다.
- 정밀 CCTV·안전시설 출처, 지면에 붙은 파란색 경로, 구간별 안전도 정보, 직접/AI 검색, 계단 가중치와 경로 추천 로직은 main 구현을 유지합니다.

인천광역시 미추홀구를 대상으로 하는 **Digital Twin 기반 안전한 골목 탐색 서비스**의 MVP입니다.

현재 MVP는 OpenStreetMap 보행 도로와 공식 건물 공간정보에 더해, 가로등·방범 CCTV·안전시설 접근성의 상대 점수를 독립적으로 저장하고 종합 안전도를 표시하는 구조를 제공합니다. CCTV와 AI-ready 안전시설은 원천 파일/인증 설정 후 배치 적재합니다.

## 현재 구성

```text
Browser
  -> OpenStreetMap tile server (direct HTTPS tile request)
  -> React frontend (Nginx, localhost:3000)
     -> /api/* reverse proxy
     -> FastAPI backend (localhost:8000)
     -> PostgreSQL + PostGIS
```

외부 데이터 수집과 전처리는 상시 서비스와 분리된 `data_pipeline/`에서 배치로 수행할 예정입니다.

## 요구 사항

- Docker Desktop 또는 Docker Engine
- Docker Compose v2 이상

## 실행

먼저 예제 환경변수를 복사합니다.

PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

`.env`의 `POSTGRES_PASSWORD`를 로컬 환경에 맞게 변경한 뒤 실행합니다.

```bash
docker compose up --build
```

다른 터미널에서 OSM 수집부터 적재까지 실행합니다. `pipeline`은 이 명령이 실행되는 동안에만 생성되는 일회성 컨테이너입니다.

```bash
docker compose --profile tools run --build --rm pipeline run-osm
```

접속 주소:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- Road GeoJSON: http://localhost:8000/api/roads
- Streetlight safety GeoJSON: http://localhost:8000/api/safety/roads?source=osm
- Streetlight Point GeoJSON: http://localhost:8000/api/streetlights?source=michuhol-public-data
- Safety CCTV GeoJSON: http://localhost:8000/api/cctvs?source=michuhol-cctv-ai-ready
- Help Point GeoJSON: http://localhost:8000/api/help-points?source=ai-ready-help-points
- Building GeoJSON: http://localhost:8000/api/buildings?source=molit-gis-building
- Shortest route: `POST http://localhost:8000/api/routes/shortest`
- Safe route: `POST http://localhost:8000/api/routes/safe`
- FastAPI API 문서: http://localhost:8000/docs

종료:

```bash
docker compose down
```

DB 데이터까지 초기화해야 할 때만 다음 명령을 사용합니다. 이 명령은 로컬 DB 볼륨을 삭제합니다.

```bash
docker compose down --volumes
```

## Health 응답

`GET /health`는 API 프로세스 상태뿐 아니라 실제 DB 연결과 PostGIS extension을 확인합니다.

정상 응답 예시:

```json
{
  "status": "ok",
  "service": "backend",
  "database": {
    "status": "ok",
    "name": "safealley",
    "postgis_version": "3.x"
  }
}
```

DB 또는 PostGIS 확인이 실패하면 HTTP 503을 반환합니다.

## Road GeoJSON

```http
GET /api/roads
GET /api/roads?bbox=126.678,37.460,126.684,37.465
GET /api/roads?source=osm&bbox=126.678,37.460,126.684,37.465
```

응답은 `FeatureCollection`이며 geometry 좌표는 `EPSG:4326`입니다. DB에는 `EPSG:5179`로 저장됩니다.

## Building GeoJSON

```http
GET /api/buildings?source=molit-gis-building
GET /api/buildings?source=molit-gis-building&bbox=126.63,37.42,126.72,37.49
```

건물은 PostGIS에서 bbox 공간 인덱스로 필터링한 뒤 `EPSG:4326` GeoJSON `MultiPolygon`으로 반환됩니다. 원본 Polygon과 MultiPolygon은 적재 시 모두 지원하며, 실제 높이가 있을 때만 Cesium에서 3D extrusion을 사용합니다.

현재 로컬 개발 DB에는 사용자가 제공한 국토교통부 `AL_D010_28_20260909.shp`에서 미추홀구 코드 `28177`로 추출한 38,543동이 `source=molit-gis-building`으로 적재됩니다. 원본 파일은 Git에서 제외되므로 새 환경에서는 `docs/building-data.md`의 명령으로 다시 적재해야 합니다.

## 경로 API

```http
POST /api/routes/shortest
Content-Type: application/json

{
  "start": {"latitude": 37.4608, "longitude": 126.6790},
  "end": {"latitude": 37.4623, "longitude": 126.6830},
  "source": "osm"
}
```

같은 요청 body를 `POST /api/routes/safe`에도 사용할 수 있습니다. 두 응답은 동일한 구조이며 `route_type`, `total_distance`, `average_safety_score`, `total_cost`, GeoJSON `geometry`, segment별 안전도와 cost 내역을 포함합니다. `total_distance`와 호환 필드 `total_distance_m`의 단위는 m입니다.

입력 좌표에서 가장 가까운 그래프 노드를 찾으며 도로 graph에서 너무 먼 좌표는 `ROUTE_SNAP_MAX_DISTANCE_M` 기준으로 거부합니다. 보행 그래프는 `footway`, `path`, `pedestrian`, `living_street`, 생활·주거·서비스 도로를 우선합니다. `primary`, `secondary`, `tertiary` 및 연결로는 OSM의 보도 태그가 부족한 지역에서 그래프가 끊기지 않도록 fallback으로 유지하되, 보도 또는 명시적 보행 허용 정보가 없으면 비용을 4배로 부여합니다. 따라서 보행자 전용·생활도로가 연결돼 있으면 해당 경로가 먼저 선택됩니다.

## Structured Output과 Tool Router

`POST /api/agent/execute`는 LLM 또는 규칙 Parser가 만든 JSON을 Pydantic으로 검증한 뒤, 명시적으로 등록된 GIS Tool만 실행합니다. 이 엔드포인트가 자연어를 직접 해석하거나 SQL을 실행하지는 않습니다.

```http
POST /api/agent/execute
Content-Type: application/json

{
  "tool": "rank_routes",
  "arguments": {
    "origin": {"latitude": 37.4608, "longitude": 126.6790},
    "destination": {"latitude": 37.4623, "longitude": 126.6830},
    "departure_time": "22:00:00",
    "profile": "pedestrian",
    "source": "osm",
    "preferences": [
      {"factor": "distance_m", "direction": "minimize", "weight": 1},
      {"factor": "streetlight_score", "direction": "maximize", "weight": 3}
    ]
  }
}
```

현재 검증된 평가 지표는 `distance_m`, `safety_score`, `streetlight_score`, `cctv_score`, `crosswalk_count`, `stairs_distance_m`, `sidewalk_coverage_percent`, `max_slope_percent`입니다. 횡단보도·계단·보도는 OSM 태그를 기반으로 합니다. 가로등은 2022년 인천시 공식 도로시설물 POI의 미추홀구 3,884건을 사용하지만, 현재 점등 여부나 2차선 미만 골목의 전체 조도를 보증하지 않습니다. 경사는 명시적 OSM `incline` 태그 또는 출처가 명시된 고해상도 DEM으로 계산하며, 현재 실제 DEM이 적재되지 않아 미측정 구간은 0으로 추정하지 않습니다. 공식 횡단보도 POI는 별도 테이블에 보존하고, 근접만으로 실제 횡단했다고 판단하지 않습니다. `population_score`는 실제 유동인구 데이터가 적재되기 전까지 지원 지표로 노출하지 않습니다. Router는 경로 후보 생성과 지표 기반 순위 평가를 분리하며, 후보마다 요청 지표가 모두 존재할 때만 점수를 계산합니다. 등록됐더라도 데이터가 없는 지표와 `police_accessibility` 같은 미등록 조건은 다른 값이나 0점으로 대체하지 않고 `unsupported_preferences`로 반환합니다. 모든 요청 조건이 미지원이면 후보는 반환하되 최종 경로는 선택하지 않습니다. 현장 미검증 `major_road_fallback` 구간을 포함한 후보는 최종 추천에서 제외하며, 모든 후보가 해당하면 후보만 보여주고 현장 검토 필요 상태로 응답합니다. 자료 출처와 검증 범위는 [보행 데이터·품질 문서](docs/pedestrian-data-quality.md)에 정리했습니다.

`departure_time`이 20:00 이상 또는 06:00 미만이면 야간 정책을 적용합니다. 사용자가 조건을 생략한 야간 요청은 거리와 함께 안전도·가로등·CCTV를 기본 평가하고, 사용자가 지정한 안전 관련 조건에도 야간 가중치를 적용합니다. 주간에 조건을 생략하면 최단거리를 기본값으로 사용합니다. 이는 실시간 유동인구나 운영 여부를 추정하는 기능이 아니라 입력 시각에 따른 명시적 경로 평가 정책입니다.

### 사용자 선택 기반 경로 개인화

AI 검색의 지시문 경량화·분석 캐시 설정, 요청 내 도로 그래프 재사용,
교차로 지표 선택 저장 수정은 [AI 검색 처리 문서](docs/ai-search-performance.md)를 참고합니다.

`rank_routes`는 빠른 길(`shortest`), 기존 경로와 겹침을 줄인 균형 길(`balanced`), 안전 길(`safe`) 후보를 생성합니다. 최종 추천이 확정되고 `user_id`가 있는 요청만 후보 지표 요약을 서버에 저장하고 `recommendation_id`를 반환합니다. 사용자가 경로를 선택하면 다음 API로 명시적인 선택을 기록합니다.

### 추천 이유와 자료 한계

`recommendation_reason`은 실제 선택 기준과 경로 거리를 한두 문장으로 설명하고, `recommendation_notes`는 비교 근거·제외한 후보·자료의 한계를 API로 전달합니다. 화면은 기존 추천 아이콘과 “왜 이 길을 추천했나요?” 및 조건별 비교를 표시하며, 별도의 자료 한계 펼침 영역은 표시하지 않습니다. 설명은 검증 가능한 경로 지표로 결정적으로 생성하며 LLM이 밝기·범죄 위험·현장 통행 가능성을 추측하지 않습니다. CCTV와 가로등은 단순 개수나 추상적인 점수로 말하지 않고 시설까지의 거리·주변 밀도·시설이 드문 구간을 종합한 비교라고 설명합니다. 낮에는 가로등을 안전도와 설명의 비교 근거에서 제외합니다. 비교는 보행 근거가 부족한 큰 도로 구간과 회피 조건 미충족 후보를 제외한 서로 다른 경로 사이에서만 수행하며, 작은 거리 차이를 우수성으로 과장하지 않습니다. 보류 시에는 그 이유를 명시하고 추천 이력도 저장하지 않습니다.

여러 조건을 요청하면 가장 비중이 큰 조건과 다음 조건을 함께 설명하고, 추천 점수가 가장 높은 유효 대안과의 거리 차이를 표시합니다. 조건별 카드에는 요청한 각 조건의 비교 결과를 넣습니다. OSM에 기록된 횡단보도·계단이 0개/0m이거나 확인된 보행공간 비율이 0%여도 현장에 실제로 없다는 뜻으로 해석하지 않으며, 측정값 자체가 없는 조건은 0으로 대체하지 않고 미지원으로 안내합니다.

API는 실제 비교에 사용한 후보를 `compared_route_type`으로 반환하고, `recommendation_criteria`에 조건별 `better/similar/worse/not_compared/unavailable` 판정과 근거 수준을 제공합니다. 화면은 이를 “추천 경로 우세·차이 거의 없음·비교 경로 우세·비교 불가”로 바꿔 표시합니다. 거리 합산은 근거 높음, 공개 시설 좌표 기반 상대 비교는 근거 보통, OSM 기록 완전성이나 대표 좌표 반경에 의존하는 계단·횡단보도·보도·교차로·경사는 근거 낮음으로 안내합니다.

후보 간 순위 계산에 사용하는 `preference_score`는 해당 검색의 후보만 상대 비교해 0·100이 될 수 있으므로 화면에 절대 점수처럼 표시하지 않습니다. 시설 위치 기반 `safety_score`도 실제 안전 확률이 아닙니다. 고해상도 DEM이 적재되지 않은 현재 상태에서 미측정 경사를 평지로 설명하지 않습니다.

```http
POST /api/agent/route-selections
Content-Type: application/json

{
  "recommendation_id": "2666a33d-ea69-43e5-b3ae-fdf9a95fb8f3",
  "user_id": "anonymous-browser-id",
  "selected_route_type": "safe"
}
```

서버는 클라이언트가 보낸 임의 점수가 아니라 해당 추천 시점에 저장한 후보 지표를 비교하여 `distance_m`, `safety_score`, `streetlight_score`, `cctv_score` 선호를 지수이동평균으로 갱신합니다. 동일 사용자의 관측이 3회 이상 쌓인 지표만 다음 무조건 요청의 가중치로 사용합니다. 현재 요청에 자연어로 명시된 조건은 학습 선호보다 우선합니다.

이 기능에서 `user_id`는 로그인 계정이 아니라 PoC용 가명 식별자입니다. 사람의 성격이나 장애 여부를 추론하지 않고 경로 선택 성향만 저장합니다. 운영 전에는 인증·동의·보존기간·초기화 기능을 추가해야 합니다.

Tool 이름은 allowlist로 제한되고, 추가 JSON 필드와 임의 Tool 이름은 HTTP 422로 거부됩니다. 지표를 확장할 때는 Tool을 새로 늘리는 대신 `backend/app/services/route_metrics.py`의 registry에 검증된 계산 함수를 등록합니다.

### 로컬 LLM 자연어 입력

`POST /api/agent/query`는 한 문장에서 출발 장소, 도착 장소, 출발 시각, 경로 선호조건을 로컬 Ollama의 `qwen3:4b` Structured Output으로 추출합니다. 장소명은 SQL이나 좌표로 자유 생성하지 않고 직접 검색과 동일한 Resolver가 실제 좌표로 변환합니다. Resolver는 `places`의 이름·별칭·주소를 정규화하여 먼저 검색하고, 로컬 결과가 없을 때만 로드된 미추홀구 OSM 도로 bbox로 제한한 공식 Nominatim 검색을 사용합니다. fallback 결과는 `source=nominatim-osm`으로 기존 `places`에 캐시됩니다. 변환된 좌표와 검증된 조건만 동일한 Tool Router로 전달됩니다. 기존 클라이언트를 위해 `origin`과 `destination` 좌표를 직접 전달하는 방식도 유지합니다.

```http
POST /api/agent/query
Content-Type: application/json

{
  "query": "밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘",
  "source": "osm"
}
```

Ollama가 실행 중이어야 하며 기본 설정은 `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `OLLAMA_MODEL=qwen3:4b`, `OLLAMA_TIMEOUT_SECONDS=300`입니다. Windows에서는 [공식 Ollama 앱](https://ollama.com/download/windows)을 설치하고 실행한 다음, 새 PowerShell 창에서 모델을 내려받습니다.

```powershell
winget install --id Ollama.Ollama --exact --source winget
ollama pull qwen3:4b
ollama list
docker compose up -d --build backend frontend
```

Ollama 앱이 실행되지 않았다면 시작 메뉴에서 Ollama를 실행하거나 별도 터미널에서 `ollama serve`를 실행합니다. `http://localhost:3000`의 **AI 검색**에서 위 예시 질문으로 확인할 수 있습니다. 첫 요청은 모델 로딩과 GPU 초기화 때문에 수 분 걸릴 수 있습니다. 이를 위해 모델 요청은 기본 300초, 프론트엔드의 AI 검색 프록시는 의미 검증 재시도까지 고려해 660초 대기합니다. 환경변수를 바꿨다면 `docker compose up -d --build --force-recreate backend`로 컨테이너를 다시 생성합니다.

모델 연결 실패는 HTTP 503, 스키마에 맞지 않는 출력은 HTTP 502로 반환합니다. 오류가 발생해도 규칙 Parser로 조용히 대체하지 않습니다. 장소를 찾지 못하면 HTTP 404로 명확히 중단하며 다른 장소로 임의 대체하지 않습니다.

초기 `places` 데이터는 주안역과 공식 도움시설(경찰·소방·응급의료) 중심의 작은 demo subset입니다. Nominatim fallback은 사용자 검색에 의한 소량 요청을 위한 MVP 기능이며 `NOMINATIM_BASE_URL`, `NOMINATIM_USER_AGENT`, `NOMINATIM_TIMEOUT_SECONDS`로 설정합니다. 운영 데이터는 OSM 또는 권위 있는 기관의 역·학교·공공시설을 파이프라인으로 미리 적재하고 별칭을 관리해야 합니다.

## 가로등 기반 상대 안전지표

원본 `data_pipeline/raw/streetlights/인천광역시 미추홀구_가로등_20240806.csv`는 CP949, WGS84 좌표의 5,313개 가로등입니다. 원본과 처리 산출물은 Git에서 제외됩니다. 전체 파이프라인은 다음 명령으로 다시 실행합니다.

```bash
docker compose --profile tools run --build --rm pipeline run-streetlight-safety \
  --source michuhol-public-data --road-source osm --source-encoding cp949
```

분석은 원본 OSM 그래프를 변경하지 않고 별도 `road_safety_segments`에 20m 이하 구간을 생성합니다. DB 계산 좌표계는 EPSG:5179이며 API GeoJSON은 EPSG:4326입니다.

```text
distance_score = 100 * (1 - percentile_rank(nearest_light_distance_m))
density_score  = 100 * percentile_rank(light_density)
gap_score      = 100 * (1 - percentile_rank(dark_gap_proxy_m))
safety_score   = distance_score * 0.4 + density_score * 0.3 + gap_score * 0.3
```

`dark_gap_proxy_m`는 5m 간격 표본점 중 최근접 가로등 거리가 가장 큰 값입니다. 밀도 계산은 평행도로 혼입을 줄이기 위해 가로등을 먼저 가장 가까운 원본 도로에 매칭합니다. 30m 반경과 점수 가중치는 `.env`의 `STREETLIGHT_*` 설정으로 변경합니다.

이 점수는 국가 공식 안전점수가 아니라 **미추홀구 가로등 공간 분포 내 상대 순위로 만든 프로젝트 자체의 조명 접근성 지표**입니다.

## CCTV·AI-ready 안전시설·종합 안전도

CCTV 기본 운영 원천은 이미 미추홀구 생활방범 데이터로 정제된 다음 AI-ready GeoJSON입니다. 로컬 적재에는 API URL, 인증키, 설치목적 재필터링이 필요하지 않습니다.

```text
data_pipeline/raw/cctvs/cctv_michuhol_ai_ready.geojson
```

```bash
docker compose --profile tools run --rm pipeline load-cctvs
```

AI-ready 파일은 다음 위치에 그대로 둡니다. CSV 재병합·geocoding·새 GeoJSON 생성은 하지 않습니다.

```text
data_pipeline/raw/help_points/help_points_michuhol_routing_ready.geojson
```

```bash
docker compose --profile tools run --rm pipeline load-help-points
docker compose --profile tools run --rm pipeline analyze-safety-components
```

공간 계산은 EPSG:5179(m), API GeoJSON은 EPSG:4326입니다. CCTV 점수는 최근접 거리·30m 밀도·5m 표본 공백 대리값의 상대 순위이고, Help Point 점수는 최근접 유효 Point 거리의 상대 순위입니다.

```text
cctv_score = cctv_distance_score * 0.4
           + cctv_density_score  * 0.3
           + cctv_gap_score      * 0.3

help_point_score = 100 * (1 - percentile_rank(nearest_help_point_distance_m))

safety_score = streetlight_score * 0.4
             + cctv_score        * 0.4
             + help_point_score  * 0.2

risk = (100 - safety_score) / 100
safe_cost = distance_m * distance_weight
          + distance_m * risk * risk_weight
```

가중치는 `.env`의 다음 항목에서 변경합니다.

- `SAFETY_STREETLIGHT_WEIGHT`, `SAFETY_CCTV_WEIGHT`, `SAFETY_HELP_POINT_WEIGHT`
- `SAFE_ROUTE_DISTANCE_WEIGHT`, `SAFE_ROUTE_RISK_WEIGHT`

안전도 구성 가중치를 변경한 뒤에는 pipeline을 다시 실행하여 DB의 `safety_score`를 갱신해야 합니다. 경로 cost 가중치는 backend 재시작 후 바로 적용됩니다.

가로등 분석 실행 전 `OSM_SAFETY_SCORE_MODE=demo`는 PT용 임시값을 생성합니다. 분석 실행 후에는 파생 구간 점수의 길이 가중 평균이 원본 도로의 `streetlight_score`와 `safety_score`에 반영되어 안전 경로 탐색에서도 사용됩니다.

운영 기본 CCTV 원천은 정밀 좌표가 검증된 `michuhol-cctv-ai-ready` GeoJSON입니다. 전국 표준 CSV 전처리 기능은 별도 원천 검증을 위한 보조 경로이며 기본 적재·분석 소스를 변경하지 않습니다. 경찰·소방·응급의료 Help Point도 검증된 `ai-ready-help-points` 원천을 기본으로 사용합니다.

테스트 실행:

```bash
docker compose exec backend pytest -q
docker compose exec backend python -m evals.evaluate_recommendation_explanations
```

두 번째 명령은 CCTV 우세와 거리 손해, 거리 우세와 CCTV 손해, 계단·횡단보도 0값, 교차로 우회, 경사 자료 부족, 현장 검토 보류, 미세한 거리 차이를 다루는 독립 설명 평가셋을 실행합니다. 설명이 실제 결과와 반대이거나, 시설 개수·현장 안전을 과장하거나, 불리한 조건을 누락하면 실패합니다.

## 디렉터리

- `frontend/`: React 및 CesiumJS UI
- `backend/`: FastAPI와 PostGIS 조회 API
- `data_pipeline/`: 외부 데이터 수집·전처리·적재 배치
- `database/`: PostGIS 최초 초기화 SQL
- `docs/`: 아키텍처와 데이터 출처 문서

## OSM 데이터 파이프라인

```text
Overpass API
  -> data_pipeline/raw/osm/michuhol_roads.json
  -> 미추홀구 area 및 보행 가능 highway 필터
  -> OSM way를 연속 node-to-node edge로 분할
  -> data_pipeline/processed/osm/road_segments.geojson
  -> EPSG:5179 변환 및 PostGIS road_segments 적재
```

`raw/`와 `processed/` 산출물은 Git에서 제외됩니다. OSM 재적재는 하나의 트랜잭션에서 `source='osm'` 행을 교체합니다. 상세 명령과 필터 기준은 `data_pipeline/README.md`를 참고하세요.

OSM 데이터는 ODbL 조건으로 제공됩니다. 화면과 `NOTICE.md`에 OpenStreetMap attribution을 포함합니다.

## 지도 레이어 요청 구조

```text
tile.openstreetmap.org --direct--> Browser/CesiumJS

PostGIS road_segments        -> FastAPI /api/roads ---------+
PostGIS road_safety_segments -> FastAPI /api/safety/roads --+
PostGIS streetlights         -> FastAPI /api/streetlights ---+-> Browser/CesiumJS overlay
PostGIS buildings            -> FastAPI /api/buildings ------+
PostGIS cctvs                -> FastAPI /api/cctvs -----------+
PostGIS help_points          -> FastAPI /api/help-points -----+
```

OSM 타일은 FastAPI나 Nginx의 `/api` 프록시를 거치지 않습니다. 공용 OSM 타일은 개발·PT 수준의 대화형 지도에만 사용하고, 서비스 트래픽이 커지면 OSM Tile Usage Policy에 맞는 별도 제공자를 선택해야 합니다.

`collect-cctvs`와 `preprocess-cctvs`는 이전 API 방식의 재현을 위한 legacy 명령으로만 남아 있으며 기본 운영 경로에서는 호출하지 않습니다.
---

<details>
<summary>GitLab Initial commit README 안내문 보존</summary>



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

* [Create](https://docs.gitlab.com/user/project/repository/web_editor/#create-a-file) or [upload](https://docs.gitlab.com/user/project/repository/web_editor/#upload-a-file) files
* [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin http://192.168.0.231/pilot2/safealley.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

* [Set up project integrations](http://192.168.0.231/pilot2/safealley/-/settings/integrations)

## Collaborate with your team

* [Invite team members and collaborators](https://docs.gitlab.com/user/project/members/)
* [Create a new merge request](https://docs.gitlab.com/user/project/merge_requests/creating_merge_requests/)
* [Automatically close issues from merge requests](https://docs.gitlab.com/user/project/issues/managing_issues/#closing-issues-automatically)
* [Enable merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)
* [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

* [Get started with GitLab CI/CD](https://docs.gitlab.com/ci/quick_start/)
* [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/user/application_security/sast/)
* [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/topics/autodevops/requirements/)
* [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/user/clusters/agent/)
* [Set up protected environments](https://docs.gitlab.com/ci/environments/protected_environments/)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
</details>
