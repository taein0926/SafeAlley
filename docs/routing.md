# 보행 경로 탐색과 추천

## 흐름·보행 정책

routes API / agent rank_routes → route_service → road_repository →
services/routing → route_ranking_service → EPSG:4326 GeoJSON LineString.

화면 검색은 최단·맞춤 후보만 생성하고 요청 내 그래프를 공유합니다.
숨겨진 균형 후보로 차이를 연출하지 않습니다. 단일 좌표 shortest/safe API는 유지합니다.

현재 pedestrian_priority.py는 보행 전용/보도가 확인된 구간 밖의 거리를 먼저 최소화하고,
그다음 요청 비용을 최소화하는 사전식 Dijkstra를 사용합니다.
분류가 없는 legacy/sample 그래프는 astar.py의 A*를 사용합니다.
전체 서비스를 순수 거리 A*라고 설명하지 않습니다.

footway/path/pedestrian/steps/living_street 및 보도가 확인된 도로를 우선하며
허용된 일반 도로로 연결을 보완합니다. 통행금지·강한 회피를 무시하지 않습니다.
최단은 같은 보행 우선 기준에서 거리를 최소화하므로 무조건적인 전체 도로 최단거리와 다를 수 있습니다.

## 공통 구간 비용

services/routing/safety_cost.py:

```text
cost = d × distance_weight
     + d × risk × risk_weight
     + (계단이면 d × stairs_weight × 2, 아니면 0)
     + crossing_cost_units × crossing_weight × 80
     + (중심선 fallback이면 d × (pedestrian_weight + 2 × crossing_weight), 아니면 0)
     + 기존 intersection penalty (호환 API)
```

d는 m, 80은 등록 건널목의 m 상당 비용이며 대기 시간/금액이 아닙니다.
기존 intersection 항은 지상 교차로 주변 길이 × intersection_weight × 4입니다.
현재 화면 검색은 대표점 교차로 비용 대신 OSM 건널목 비용을 사용합니다.

- risk=(100-effective_score)/100. 높을수록 시설 위험 비용은 작습니다.
- 밤에는 저장된 종합 안전도, 낮에는 가로등을 제외한 CCTV/안전시설 비율을 재정규화합니다.
- 맞춤은 요청된 safety/streetlight/CCTV 점수의 가중 평균을 사용합니다.
  risk_weight=SAFE_ROUTE_RISK_WEIGHT × 시설 선호 합 / (시설+거리 선호 합).
  거리 계수 1, pedestrian 계수 0.5입니다.
- 최단 risk 계수는 0. 단일 route API의 stairs_weight 기본 0은 추가 계단 비용이 없습니다.
- 안전 route의 기본 거리/위험 가중치는 1 / 5입니다. 로컬 .env 또는 VM private/service-env/backend.env에서 설정합니다.
- stairs/crossing 가중치는 0–1. 계단은 safety_score 자체에 섞지 않습니다.

명시적인 avoid는 별도 강한 조건입니다. 무계단 요청은 계단 edge를 허용하지 않고
경로가 없으면 조용히 완화하지 않습니다. stairs_weight=1만으로 통행 금지를 뜻하지는 않습니다.
건널목 회피의 추가 우회는 같은 다른 조건의 기준 경로에서 min(30%,300m)로 제한합니다.
가중치 조절 후보를 비교하는 구현이며 전역 자원제약 최적해를 보장하지 않습니다.

## UI → API

세 단계 값은 0/50/100, 초기값은 모두 50입니다.

| UI | backend mapping |
| --- | --- |
| 경로 우선순위 | distance_m minimize=100-값, safety_score maximize=값 |
| 계단 회피 | stairs_weight=값/100, stairs_distance_m minimize 선호 |
| 건널목 회피 | crossing_weight=값/100, crosswalk_count minimize 선호 |
| 출발 시각 | departure_time, 한국 현지 HH:mm |

0인 선호는 생략합니다. 경사 회피는 추천 조건으로 지원하지 않습니다.
OSM의 incline과 선택적 DEM 경사 메타데이터는 응답에 보존하지만 경로 비용·추천 순위에는 반영하지 않습니다.

## 결과와 한계

- total_distance/total_distance_m은 m, 평균 안전도는 도로 길이 가중 평균이며 안전 확률이 아닙니다.
- 계단 metadata: highway/is_steps, 원본에 있으면 incline/step_count/ramp/wheelchair/handrail.
- 등록 건널목 집계와 전체 횡단 수 비교를 구분하고, 불완전한 자료를 0으로 단정하지 않습니다.
- 육교는 실제 OSM 입체 연결/참조 매칭을 사용합니다. 독립 강제 경유 가중치는 없습니다.
- 예상 시간=ceil(거리/1.2m/s/60). 신호 대기·계단 지연·개인 속도는 미반영입니다.
- 후보 동일성은 segment ID 순서, 없으면 geometry 좌표 순서입니다. 동일 후보는 하나만 표시합니다.
- 미검증 대로 metadata는 내부 후보 비교에 남지만 폐기한 대로 경고를 결과에 추가하지 않습니다.
- 미지원 조건은 unsupported로 전달하며 다른 시설 지표로 몰래 대체하지 않습니다.

[테스트](testing.md), [시설 점수 구축](data-pipeline.md).
