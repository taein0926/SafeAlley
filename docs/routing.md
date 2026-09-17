# Phase 4 routing

`POST /api/routes/shortest`와 `POST /api/routes/safe`의 호출 흐름은 다음과 같습니다.

```text
API route
  -> route_service (흐름 조정 및 GeoJSON 생성)
  -> road_repository (최근접 노드 및 도로 조회)
  -> routing.graph (방향성 인접 리스트 구성)
  -> routing.safety_cost (경로별 cost 정책)
  -> routing.astar (주입된 cost 정책 기반 A*)
```

## 좌표계

- DB geometry와 A* 휴리스틱 거리: EPSG:5179, 단위 m
- 입력 및 GeoJSON 응답: EPSG:4326

그래프 노드는 현재 `road_segments.source_node_id`, `target_node_id`와 각 geometry의 시작점/끝점에서 파생합니다. MVP sample 규모에는 충분하지만, 실제 OSM 데이터를 적재할 때는 노드 좌표 일관성 검증과 별도 `road_nodes` 테이블 또는 캐시를 검토합니다.

## Cost와 휴리스틱

- 최단 경로 cost: 각 segment의 `length_m`
- 안전 경로 cost: `distance_m * distance_weight + distance_m * normalized_risk * risk_weight`
- `normalized_risk`: `(100 - safety_score) / 100`
- 휴리스틱: EPSG:5179 노드 직선거리 × 최소 거리 cost 가중치
- 일방통행: `forward_allowed`, `reverse_allowed`에 따라 방향 edge 생성

경로의 `average_safety_score`는 segment 길이로 가중한 평균입니다. 따라서 긴 구간이 짧은 구간보다 경로 전체 안전도에 더 크게 반영됩니다.

안전도와 경로 가중치는 루트 `.env`에서 관리합니다. 구성 안전도 가중치 변경은 pipeline 재적재가 필요하고, 경로 거리/위험 가중치 변경은 backend 재시작으로 반영됩니다.
