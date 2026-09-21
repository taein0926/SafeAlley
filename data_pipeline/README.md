# Data Pipeline

보행 경사, 인천시 공식 횡단보도 POI, 경로망 검증 절차는 [보행 데이터·품질 문서](../docs/pedestrian-data-quality.md)를 참고합니다.

외부 공간 데이터의 수집, 전처리, 좌표계 변환 및 PostGIS 적재를 담당할 독립 배치 영역입니다.

Phase 5에서는 OpenStreetMap의 미추홀구 보행 가능 도로를 수집·정제·적재합니다.

건물 파이프라인은 공식 i-Map 또는 공식 대체 원천에서 사용자가 내려받은 SHP/GeoJSON/GPKG를 입력으로 받습니다. 확인되지 않은 내부 API를 호출하는 collector는 제공하지 않습니다.

- `collectors/`: 외부 원본 수집
- `preprocess/`: 정제, 좌표 변환, topology 및 안전도 전처리
- `loaders/`: PostGIS 적재
- `raw/`: 원본 데이터 로컬 보관(Git 제외)
- `processed/`: 처리 결과 로컬 보관(Git 제외)

## 가로등 분석 파이프라인

사용자 제공 공식 파일 `인천광역시 미추홀구_가로등_20240806.csv`(CP949, 5,313행)를 `raw/streetlights/`에 둡니다. CSV의 WGS84 Point를 검증해 `processed/streetlights/streetlights.geojson`으로 만들고 EPSG:5179 `streetlights`에 적재한 뒤 분석합니다.

```bash
docker compose --profile tools run --build --rm pipeline run-streetlight-safety \
  --source michuhol-public-data --road-source osm --source-encoding cp949
```

단계별 명령은 `preprocess-streetlights`, `load-streetlights`, `analyze-streetlights`입니다. 분석은 원본 `road_segments`를 수정·분할하지 않고 `road_safety_segments`만 재생성합니다. 최근접 거리와 5m 샘플 암부 대리값은 GiST KNN, 30m 밀도는 `ST_DWithin`으로 계산하며 Python 이중 반복을 사용하지 않습니다.

설정은 `STREETLIGHT_SEGMENT_LENGTH_M`, `STREETLIGHT_SEARCH_RADIUS_M`, `STREETLIGHT_SAMPLE_INTERVAL_M`, `STREETLIGHT_DISTANCE_WEIGHT`, `STREETLIGHT_DENSITY_WEIGHT`, `STREETLIGHT_GAP_WEIGHT`입니다. `STREETLIGHT_CANDIDATE_SEARCH_RADIUS_M`는 정확한 최근접 결과를 바꾸지 않는 쿼리 최적화 반경이며, 후보가 없으면 KNN으로 보완합니다. 분석 반경과 시각화 등급은 프로젝트용 파라미터이며 공식 설치·안전 기준이 아닙니다.

## 실행

OSM 전체 흐름:

```bash
docker compose --profile tools run --build --rm pipeline run-osm
```

단계별 실행:

```bash
docker compose --profile tools run --rm pipeline collect-osm
docker compose --profile tools run --rm pipeline preprocess-osm
docker compose --profile tools run --rm pipeline load-osm
```

산출물:

- `raw/osm/michuhol_roads.json`: Overpass 원본 JSON
- `raw/osm/michuhol_roads.meta.json`: endpoint, area, 실행 query 기록
- `processed/osm/road_segments.geojson`: 보행 graph edge GeoJSON

## 보행 도로 규칙

- 미추홀구 `boundary=administrative`, `admin_level=6` Overpass area 사용
- 보행 가능한 생활도로, 보행로, 계단, 서비스도로와 일반 도로만 허용
- `foot=no/private`, 별도 허용 없는 `access=no/private`, `area=yes` 제외
- motorway, trunk, construction, proposed 등 보행 부적합 유형 제외
- 차량용 `oneway`는 보행 방향에 적용하지 않고 `oneway:foot`만 반영
- way의 각 연속 OSM node 쌍을 하나의 graph edge로 생성
- `OSM_MIN_SEGMENT_LENGTH_M`보다 짧은 극소 edge 제외(기본 1m)

`load-osm`은 트랜잭션 안에서 기존 `source='osm'` 데이터를 교체합니다. 오류가 발생하면 삭제와 적재가 모두 롤백됩니다.

## 설정

공식 공개 Overpass endpoint는 `.env`의 `OVERPASS_API_URL`에서 교체할 수 있습니다. 공용 서버 과부하 시 재시도하거나 검증된 다른 endpoint를 지정하세요. `OSM_AREA_NAME`, `OSM_AREA_ADMIN_LEVEL`, timeout, User-Agent도 `.env`에서 관리합니다.

`OSM_SAFETY_SCORE_MODE=demo`에서는 PT 시각화를 위해 `source_id` 기반의 재현 가능한 의사난수로 빨강(20–54), 노랑(55–74), 초록(75–100) 점수를 대략 균등하게 배정합니다. 매번 pipeline을 실행해도 같은 segment는 같은 점수를 받습니다. `uniform` 모드에서는 `OSM_DEFAULT_SAFETY_SCORE`가 적용됩니다. 실제 안전 데이터를 연결하기 전에는 이 값을 분석이나 의사결정에 사용하면 안 됩니다.

안전도 구성 가중치는 루트 `.env`의 `SAFETY_STREETLIGHT_WEIGHT`, `SAFETY_CCTV_WEIGHT`, `SAFETY_HELP_POINT_WEIGHT`에서 관리합니다. 값을 바꾼 뒤 분석 명령을 다시 실행해야 저장된 `safety_score`가 갱신됩니다.

테스트:

```bash
docker compose --profile tools run --rm --entrypoint python pipeline -m pytest -q
```

## 건물 파일 전처리 및 적재

공식 데이터 파일과 출처 확인 방법은 `docs/building-data.md`를 먼저 읽습니다. 파일은 `raw/buildings/`에 두고, 다음 세 방법 중 하나로 미추홀구 범위를 명시해야 합니다.

구분 필드 사용 예시:

```bash
docker compose --profile tools run --build --rm pipeline run-buildings \
  --input /pipeline/raw/buildings/buildings.gpkg \
  --district-field SIGUNGU_NM \
  --district-value 미추홀구 \
  --source imap \
  --source-dataset "공식 데이터셋명"
```

경계 파일 사용 예시:

```bash
docker compose --profile tools run --build --rm pipeline run-buildings \
  --input /pipeline/raw/buildings/buildings.shp \
  --boundary /pipeline/raw/buildings/michuhol_boundary.geojson \
  --field-map /pipeline/config/buildings.field-map.example.json \
  --source imap \
  --source-dataset "공식 데이터셋명"
```

이미 공식적으로 미추홀구만 포함한 파일인 경우에만 `--assume-michuhol-only`를 사용할 수 있습니다. 파일에 CRS가 없으면 `--source-crs EPSG:5179`처럼 명시합니다. EPSG 코드는 실제 메타데이터를 확인한 값만 사용합니다.

처리 결과는 `processed/buildings/buildings.geojson`에 EPSG:4326으로 생성되고, 로더는 Polygon/MultiPolygon을 PostGIS `geometry(MultiPolygon,5179)`로 정규화해 저장합니다. 높이나 층수가 원본에 없으면 `null`로 유지합니다.

### 제공된 국토교통부 인천 GIS건물통합정보

`AL_D010_28_20260909.zip`은 인천 전체 309,863동을 포함합니다. 압축 해제한 SHP의 원본 CRS는 EPSG:5186이고 DBF 한글 인코딩은 CP949입니다. `A23=28177`로 미추홀구 38,543동을 선택합니다.

```bash
docker compose --profile tools run --build --rm pipeline run-buildings \
  --input /pipeline/raw/buildings/molit_gis_building_20260909/AL_D010_28_20260909.shp \
  --district-field A23 \
  --district-value 28177 \
  --source-encoding CP949 \
  --field-map /pipeline/config/molit-gis-buildings-20260909.field-map.json \
  --source molit-gis-building \
  --source-dataset "국토교통부_GIS건물통합정보_20260909"
```

`--source-encoding`은 `.cpg`가 없는 SHP의 DBF 문자 인코딩을 명시합니다. 필드 매핑의 배열 값은 여러 원본 필드를 공백으로 연결하며, 이 파일에서는 `A4` 법정동명과 `A5` 지번으로 주소를 만듭니다.

## CCTV와 AI-ready Help Point

CCTV 공식 원천은 공공데이터포털 데이터 ID `15096428`입니다. 활용신청 후 확인한 요청 URL과 키를 각각 `DATA_GO_KR_CCTV_API_URL`, `DATA_GO_KR_SERVICE_KEY`에 설정합니다. collector는 임의 endpoint를 기본값으로 사용하지 않습니다.

```bash
docker compose --profile tools run --rm pipeline collect-cctvs
docker compose --profile tools run --rm pipeline preprocess-cctvs
```

`preprocess-cctvs`가 출력한 실제 `purpose_counts`를 검토한 뒤에만 `SAFETY_CCTV_PURPOSES`를 설정합니다. 모든 원본 record를 `cctvs`에 보존하되 유효 좌표와 일치 목적을 가진 행만 `is_safety_cctv=true`로 분석합니다.

Help Point operational source는 아래 단일 GeoJSON입니다.

```text
raw/help_points/help_points_michuhol_routing_ready.geojson
```

```bash
docker compose --profile tools run --rm pipeline load-help-points
docker compose --profile tools run --rm pipeline analyze-safety-components
```

validation은 Point geometry의 `[longitude, latitude]`를 source of truth로 사용합니다. 좌표 누락·비 Point·비수치·범위 오류 Feature는 이유와 식별자를 출력하고 제외하며 나머지 pipeline은 계속됩니다. properties는 JSONB로 보존합니다.

`analyze-safety-components`는 CCTV 최근접 거리·30m 개수/밀도·5m 표본 공백 대리값과 Help Point 최근접 거리를 EPSG:5179에서 계산합니다. 동일 좌표의 CCTV는 하나의 관측 위치로 집계해 저정밀 원본의 중복이 밀도 점수를 부풀리지 않게 합니다. 결과는 `road_safety_segments`의 component/raw metric에 독립 저장되고, 종합 점수는 기본 `0.4 * streetlight + 0.4 * cctv + 0.2 * help_point`입니다. 이 값들은 공식 안전등급이나 CCTV 촬영범위를 뜻하지 않습니다.

행정안전부 전국 CCTV 표준 CSV를 직접 내려받은 경우에는 API 키 없이 다음 명령을 사용합니다. CP949 원본에서 미추홀구를 선별하고 `생활방범`, `어린이보호`만 분석 대상으로 표시합니다.

```bash
docker compose --profile tools run --rm pipeline run-cctv-csv \
  --input /pipeline/raw/cctvs/national_cctv.csv \
  --district-name 미추홀구 \
  --cctv-source mois-cctv-standard \
  --source-encoding cp949
```

현재 미추홀구 표준 CSV의 3,176건은 모두 경도 소수점 2자리·위도 3자리 수준의 `source_approximate` 좌표다. 방범·어린이보호 3,100건은 231개 고유 좌표 셀로 반환된다. `coordinate_quality`, `coordinate_source`, 위·경도 정밀도 자릿수를 DB에 함께 저장한다. 지도는 이 값을 정확한 점으로 찍지 않고 반올림 범위 셀로 표시한다. 주소 지오코딩 결과를 적용할 때도 원본 좌표를 덮어 없애지 말고, 결과 출처와 매칭 주소를 남긴 뒤 별도 검증을 거쳐야 한다.
