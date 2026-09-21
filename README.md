# SafeAlley

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

기본 화면의 약 900m 귀가 예시에는 데모 목적지 2곳을 장소 인덱스에 추가해야 합니다. 주소 수준 좌표이므로 보행 출입구는 별도 확인이 필요합니다.

```bash
docker compose --profile tools run --build --rm pipeline load-demo-places
```

접속 주소:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- Road GeoJSON: http://localhost:8000/api/roads
- Streetlight safety GeoJSON: http://localhost:8000/api/safety/roads?source=osm
- Streetlight Point GeoJSON: http://localhost:8000/api/streetlights?source=michuhol-public-data
- Safety CCTV GeoJSON: http://localhost:8000/api/cctvs?source=mois-cctv-standard
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

지도도 성공한 자연어 해석 결과의 `departure_time`이 이 야간 구간에 속하면 OSM 바탕지도만 어둡게 표시합니다. 경로 선과 안전시설 표시 색은 유지하며, 주간·시각 미지정·검색 실패 상태에서는 기본 밝기로 돌아갑니다. 이 효과는 입력 시각을 표현할 뿐 실제 조도나 가로등 점등 상태를 나타내지 않습니다. 시간 경계 테스트는 `cd frontend && npm test`로 실행합니다.

### 사용자 선택 기반 경로 개인화

`rank_routes`는 거리 우선(`shortest`), 거리·안전 균형(`balanced`), 안전 우선(`safe`) 비용으로 각각 계산합니다. 같은 선이 나온 후보는 합쳐 실제로 구별되는 1~3개만 반환하며, 다른 길을 억지로 만들기 위한 우회 벌점은 주지 않습니다. 화면은 후보가 있으면 `balanced`를 기본 선택해 그 경로만 지도에 표시합니다. 현장 미검증으로 서버가 추천을 보류한 경우에도 화면의 기본 선택은 **검토용 표시**일 뿐 안전한 경로라는 판정은 아닙니다. 초기 예시는 주안역→그린빌라트로, 현재 적재된 도로망에서 균형 길 약 924m(세 후보 약 893~1,053m)이며 세 비용 방식의 경로가 서로 다릅니다. 그린빌라트는 [주소 확인 지점](https://jusoga.com/b/2817010500103950002214926/)의 주소 수준 좌표로 적재한 데모 목적지이며 실제 보행 출입구는 검증되지 않았습니다. 다른 출발·도착지에서 실제 경로가 겹치면 후보가 3개보다 적을 수 있습니다. `user_id`가 있는 요청은 후보의 지표 요약을 서버에 저장하고 `recommendation_id`를 반환합니다. 사용자가 경로를 선택하면 다음 API로 명시적인 선택을 기록합니다.

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

`POST /api/agent/query`는 한 문장에서 출발 장소, 도착 장소, 출발 시각, 경로 선호조건을 로컬 Ollama의 `qwen3:4b` Structured Output으로 추출합니다. 장소명은 SQL이나 좌표로 자유 생성하지 않고 `places` 테이블의 allowlisted DB Resolver가 실제 좌표로 변환합니다. 변환된 좌표와 검증된 조건만 동일한 Tool Router로 전달됩니다. 기존 클라이언트를 위해 `origin`과 `destination` 좌표를 직접 전달하는 방식도 유지합니다.

```http
POST /api/agent/query
Content-Type: application/json

{
  "query": "밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘",
  "source": "osm"
}
```

Ollama가 실행 중이어야 하며 기본 설정은 `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `OLLAMA_MODEL=qwen3:4b`, `OLLAMA_TIMEOUT_SECONDS=120`입니다. 모델 연결 실패는 HTTP 503, 스키마에 맞지 않는 출력은 HTTP 502로 반환합니다. 오류가 발생해도 규칙 Parser로 조용히 대체하지 않습니다. 장소를 찾지 못하면 HTTP 404로 명확히 중단하며 다른 장소로 임의 대체하지 않습니다.

`places`에는 현재 주안역과 공식 도움시설(경찰·소방·응급의료)이 들어 있습니다. 범용 장소 검색 범위를 넓히려면 OSM 또는 권위 있는 기관의 역·학교·공공시설 데이터를 같은 테이블에 적재하고 별칭을 관리해야 합니다. 런타임 외부 지오코딩 API에는 의존하지 않습니다.

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

CCTV 원천은 공공데이터포털 데이터 ID `15096428`인 `인천광역시 미추홀구 CCTV관리대장목록`입니다. `.env`의 `DATA_GO_KR_CCTV_API_URL`에는 인증된 공식 활용신청 화면에 표시된 요청 URL을, `DATA_GO_KR_SERVICE_KEY`에는 발급받은 키를 넣습니다. 저장소에는 임의 endpoint나 키를 포함하지 않습니다.

먼저 실제 설치목적 값과 건수를 확인한 뒤 그 값만 `SAFETY_CCTV_PURPOSES`에 쉼표로 지정합니다.

```bash
docker compose --profile tools run --rm pipeline collect-cctvs
docker compose --profile tools run --rm pipeline preprocess-cctvs
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

현재 로컬 데이터 리허설에서는 행정안전부 CCTV 표준데이터(데이터셋 `15075538`)를 직접 내려받아 미추홀구 3,176건을 선별했습니다. 이 중 설치목적이 `생활방범` 또는 `어린이보호`인 3,100건만 안전도 계산에 사용합니다. 다만 원본 경도는 주로 소수점 2자리, 위도는 3자리라 3,100건이 231개 좌표에 겹칩니다. 전처리는 이를 `source_approximate`로 표시하고 원본 건을 보존합니다. API와 지도는 같은 좌표를 하나의 **위치 셀**로 묶어 반올림 가능 범위를 표시하며, 도로 밀도 계산도 231개 고유 위치만 집계해 중복으로 점수가 부풀지 않게 합니다. 이는 실제 CCTV 설치 지점으로 보정한 것이 아니므로 정밀 좌표가 확보되기 전에는 CCTV 점수를 상대적 참고 지표로만 사용합니다. 경찰·소방·응급의료 Help Point는 각 공식 원천에서 정리한 8건을 사용합니다.

```bash
docker compose --profile tools run --rm pipeline run-cctv-csv \
  --cctv-source mois-cctv-standard --source-encoding cp949
docker compose --profile tools run --rm pipeline load-help-points \
  --help-point-source official-help-points
docker compose --profile tools run --rm \
  -e SAFETY_STREETLIGHT_WEIGHT=0 \
  -e SAFETY_CCTV_WEIGHT=0.75 \
  -e SAFETY_HELP_POINT_WEIGHT=0.25 \
  pipeline analyze-safety-components \
  --cctv-source mois-cctv-standard \
  --help-point-source official-help-points --road-source osm
```

미추홀구 공식 가로등 API는 무료·CC0이지만 활용키가 필요한 API입니다. 키가 설정되지 않은 실행에서는 가로등을 0점으로 대체해 지원하는 척하지 않고 `streetlight_score`를 미지원 지표로 반환합니다. 이때 종합 안전점수는 CCTV 75%, Help Point 25%의 상대지표이며 `properties.safety_data_status`는 `cctv-help-relative-v1`로 기록됩니다.

테스트 실행:

```bash
docker compose exec backend pytest -q
```

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

### 지도·경로 응답 최적화

- 첫 화면은 주안역 주변에서 시작하며, 안전도 도로는 현재 화면 범위의 bbox로 조회합니다. 시·구 전체를 볼 때는 세부 도로 레이어를 표시하지 않고 동네 수준으로 확대하면 불러옵니다. 카메라 이동 중에는 요청을 250ms 지연하고, 이미 받은 범위와 진행 중인 같은 범위는 재요청하지 않습니다. 경로 후보가 표시되면 안전도 도로 레이어를 숨깁니다.
- 로컬 측정에서 전체 도로 36,210개를 처음부터 받던 응답(약 33.7MB)이 주안역 시작 화면의 5,003개(약 4.7MB)로 줄었습니다. 지도 데이터 자체를 삭제하거나 경로 검색 범위를 제한한 것은 아닙니다.
- 세 경로 후보는 같은 요청에서 출발·도착 노드와 도로 그래프를 한 번만 준비해 공유합니다. 요청을 넘어서는 전역 캐시는 두지 않아 도로 데이터 갱신 후 오래된 그래프가 남지 않습니다. 동일 출발·도착의 rank_routes 실측은 약 7.2초에서 1.9초로 줄었습니다(로컬 환경 기준).
- 자연어 해석에 쓰이는 로컬 LLM 시간과 OSM 타일 네트워크 지연은 이 최적화에 포함되지 않습니다.

현재 CCTV 설치목적별 실제 건수와 Help Point category별 실제 건수는 원천 접근 설정/파일이 없으므로 문서에 임의로 기입하지 않습니다. 각 배치 명령이 실제 통계를 출력합니다.
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
