# Database Schema

## road_segments

도로 geometry, 그래프 연결 정보와 Phase 4 안전도 점수를 저장하는 edge 테이블입니다.

| Column | Type | Description |
| --- | --- | --- |
| `id` | `bigserial` | 내부 PK |
| `source`, `source_id` | `varchar` | 데이터 출처와 원본 식별자 |
| `source_node_id`, `target_node_id` | `bigint` | 향후 경로 그래프용 노드 식별자 |
| `geom` | `geometry(LineString, 5179)` | 도로 구간 |
| `length_m` | `double precision` | PostGIS에서 계산한 미터 길이 |
| `streetlight_score` | `numeric(5,2)` | 정규화된 가로등 점수, 0–100 |
| `cctv_score` | `numeric(5,2)` | 정규화된 CCTV 점수, 0–100 |
| `population_score` | `numeric(5,2)` | 정규화된 유동인구 점수, 0–100 |
| `safety_score` | `numeric(5,2)` | 세 구성 점수의 가중 평균, 0–100 |
| `properties` | `jsonb` | 원본 속성 보존 |

인덱스:

- `ix_road_segments_geom_gist`: geometry GiST
- `ix_road_segments_source_node`: 시작 노드 B-tree
- `ix_road_segments_target_node`: 종료 노드 B-tree
- `(source, source_id)`: fixture와 실제 데이터의 멱등 적재를 위한 unique index

초기 스키마는 `0001_create_road_segments.py`, 안전도 구성 점수는 `0002_add_safety_components.py` migration에서 관리합니다.

## buildings

건물 속성과 면 geometry를 도로 그래프와 분리해 저장합니다. 원본 Polygon과 MultiPolygon은 적재 시 `MultiPolygon`으로 정규화합니다.

| Column | Type | Description |
| --- | --- | --- |
| `id` | `bigserial` | 내부 PK |
| `source`, `building_id` | `varchar` | 검증된 데이터 출처와 원본 식별자 |
| `building_name`, `address`, `main_use` | `text/varchar` | 건물 기본 속성 |
| `building_area`, `total_floor_area` | `double precision` | 원본에 존재할 때만 저장하는 면적 |
| `height_m`, `floors` | `double precision/integer` | 원본에 존재할 때만 저장하는 높이·층수 |
| `source_updated_at` | `text` | 원천 데이터가 제공한 갱신값 원문 |
| `geom` | `geometry(MultiPolygon, 5179)` | 정제·정규화된 건물 geometry |
| `properties` | `jsonb` | 데이터셋명과 원본 파일 식별 정보 |

`ix_buildings_geom_gist`가 bbox 공간 조회를 지원하고 `(source, building_id)` unique 제약이 반복 적재를 멱등하게 만듭니다. 스키마는 `0003_create_buildings.py` migration에서 관리합니다.

## streetlights

원본 WGS84 경위도와 EPSG:5179 `Point` geometry, 원본 표찰 속성, 최근접 원본 도로 매칭 결과를 저장합니다. `(source, source_id)`는 unique이며 `ix_streetlights_geom_gist`와 source-aware KNN용 `ix_streetlights_source_geom_gist`가 공간 계산을 지원합니다.

## road_safety_segments

`road_segments`를 20m 이하로 나눈 분석 전용 `LineString(EPSG:5179)`입니다. `road_id` FK로 원본에 연결되며 원본의 node ID와 geometry는 바꾸지 않습니다. 최근접 거리, 주변 개수·100m 환산 밀도, 5m 샘플의 최대 최근접 거리, 세 percentile 점수와 최종 점수를 저장합니다. `(road_id, segment_index)` unique 및 geometry GiST index를 사용합니다.

두 테이블은 migration `0004`, source-aware KNN 최적화는 `0005`에서 관리합니다.
