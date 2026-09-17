# OpenStreetMap data pipeline

## 흐름

```text
collectors/osm.py
  Overpass area query
  -> raw/osm/michuhol_roads.json (EPSG:4326)

preprocess/osm_roads.py
  보행 가능 highway/access 필터
  geometry, 누락 node 및 최소 edge 길이 검증
  way를 node-to-node graph edge로 분할
  -> processed/osm/road_segments.geojson (EPSG:4326)

loaders/postgis.py
  source=osm 데이터만 트랜잭션 교체
  ST_Transform(4326 -> 5179)
  ST_Length로 length_m 계산
  -> PostGIS road_segments
```

OSM node ID를 `source_node_id`와 `target_node_id`로 사용하고, source ID는 `osm-way-{way_id}-edge-{index}` 형식으로 생성합니다. 원본 tag는 `properties.osm_tags`에 보존합니다.

## 영역 필터

기본 query는 `name=미추홀구`, `boundary=administrative`, `admin_level=6`인 Overpass area 안의 `highway` way를 요청합니다. 행정경계를 가로지르는 OSM way는 Overpass area 선택 특성상 경계에 인접한 일부 node-to-node 구간을 포함할 수 있습니다. 법정 경계에 맞춘 엄격한 geometry clip이 필요하면 별도 공식 경계 polygon을 입력으로 추가해야 합니다.

## 데이터 운영

- raw와 processed 파일은 재현·검사를 위해 호스트에 남지만 Git에는 포함하지 않습니다.
- 공개 Overpass 서버는 소규모/비정기 갱신용입니다. 자동 대량 갱신에는 별도 instance나 지역 extract를 검토합니다.
- OSM-derived 데이터나 화면을 공개할 때 `NOTICE.md` 및 UI의 attribution을 유지합니다.
- PT 환경의 `demo` 모드는 OSM `source_id` 해시를 이용해 세 색상 구간에 재현 가능한 임시 점수를 배정합니다. 실제 가로등/CCTV/유동인구를 연결할 때는 이 모드를 제거하거나 `uniform`으로 전환해야 합니다.
