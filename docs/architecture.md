# Architecture

## Current MVP

```text
User browser
  -> OpenStreetMap tile server (direct browser request)
  -> frontend (React, CesiumJS, Nginx)
     -> GET /api/roads
     -> GET /api/buildings
     -> GET /api/safety/roads, /api/streetlights
     -> POST /api/routes/shortest, /api/routes/safe
     -> FastAPI service/repository
     -> road_segments, road_safety_segments, streetlights, buildings

OpenStreetMap Overpass API
  -> data_pipeline/raw (원본 JSON)
  -> pedestrian filter + graph edge generation
  -> data_pipeline/processed (GeoJSON)
  -> data_pipeline PostGIS loader
  -> road_segments(source=osm)

MOLIT GIS building file (or verified official i-Map file)
  -> data_pipeline/raw/buildings
  -> Michuhol-gu filter + geometry validation + EPSG:4326 GeoJSON
  -> data_pipeline/processed/buildings/buildings.geojson
  -> data_pipeline PostGIS loader
  -> buildings(source=molit-gis-building or verified source name)

Michuhol-gu streetlight CSV (user-provided official file)
  -> data_pipeline/raw/streetlights (CP949, EPSG:4326)
  -> validated Point GeoJSON
  -> streetlights (EPSG:5179)
  -> PostGIS-only split/distance/density/sample/rank analysis
  -> road_safety_segments (derived; original graph topology unchanged)
```

Frontend와 backend는 `public` Docker network를 공유합니다. Backend와 database는 별도의 `private` internal network를 공유하며 frontend는 database network에 참여하지 않습니다.

`GET /health`는 실제 PostgreSQL 연결과 `PostGIS_Version()` 실행 결과를 반환합니다. Frontend는 같은 오리진의 `/api/health`를 호출하고 Nginx가 이를 backend의 `/health`로 전달합니다.

데이터 수집·전처리는 상시 서비스와 분리된 `data_pipeline/`의 일회성 배치로 구현합니다.

Pipeline은 외부 수집을 위해 `public` network와 DB 적재를 위한 `private` network에 참여합니다. raw/processed 호스트 디렉터리만 bind mount하며 frontend나 backend 내부에 수집 코드를 두지 않습니다.

Frontend는 안전도 표시에 `GET /api/safety/roads?source=osm`을 사용합니다. 기존 `GET /api/roads?source=osm`과 route 요청은 그대로 유지됩니다.

Frontend는 별도로 `GET /api/buildings?source=molit-gis-building`을 호출합니다. source는 `VITE_BUILDING_SOURCE`로 바꿀 수 있습니다. OSM 배경지도는 `OpenStreetMapImageryProvider`가 외부 타일 서버를 직접 호출하며 backend에는 타일 프록시가 없습니다.

## 좌표계 원칙

- DB 내부 저장, 거리 및 buffer 연산: `EPSG:5179`
- REST/GeoJSON 출력: `EPSG:4326`

API repository는 `ST_Transform(geom, 4326)` 후 `ST_AsGeoJSON`을 호출합니다. 선택적인 bbox 입력 역시 EPSG:4326으로 받은 뒤 DB 쿼리에서 EPSG:5179로 변환합니다.
