# DB 구조

스키마 정본은 backend/alembic/versions이며 현재 head는 **0016**입니다.
적용된 0011(정밀 CCTV 좌표 품질) 등 migration 이력은 삭제/downgrade하지 않습니다.

| 테이블 | 역할 |
| --- | --- |
| road_segments | 그래프 edge·OSM node 연결·방향·거리·시설 점수·원본 JSONB |
| road_safety_segments | 짧게 분할한 분석 구간, 시설 거리/밀도/공백 지표·구성/종합 점수 |
| buildings | 공식 GIS 건물 이름·주소·용도·면적·높이·층수·원천 속성 |
| streetlights | 등록 가로등 위치·표찰·출처 |
| cctvs | 정밀 CCTV 위치·목적·좌표 품질·원본 속성 |
| help_points | 경찰/119/병원 분류·주소·연락처·출처 |
| places | 장소명/별칭/주소·좌표, Nominatim 재사용 캐시 |
| public_crosswalks | 공식 POI/OSM 건널목 원천 Point; 임의 연결을 만들지 않음 |
| pedestrian_references | 교차로/육교 참조·검증·원천 metadata |
| weather_forecasts | 격자·발표/예보 시각별 기상 캐시 |
| solar_times | 기관·지역·날짜별 일출/일몰 |
| route_recommendations | 최종 추천·후보 지표 요약 |
| route_selection_events | 사용자 후보 선택 기록 |
| user_route_preferences | 선택 기반 선호 요약 |
| osm_display_roads | 이전 표시 전용 테이블; 호환을 위해 보존, 현재 서비스 미사용 |

공간 컬럼은 EPSG:5179와 GIST를 사용합니다. API는 ST_Transform(...,4326) 후 GeoJSON을 생성합니다.
도로 node/출처 ID에도 조회·멱등 적재용 인덱스가 있습니다.

도로 핵심: id/source/source_id, source_node_id/target_node_id, 통행 방향,
LineString geom/length_m, streetlight/cctv/help_point/population/safety 점수, properties, 시각.
점수는 0–100의 위치 기반 상대 지표입니다. population은 호환 컬럼이며 실제 연동되지 않았습니다.
계단은 properties.highway/is_steps/osm_tags로 보존하며 safety_score와 독립입니다.
road_safety_segments는 원본 topology를 바꾸지 않는 별도 분석 구간입니다.

건물 Polygon/MultiPolygon은 MultiPolygon(5179), 시설은 Point(5179)로 관리합니다.
없는 이름·높이·층수는 null이며 가상의 높이를 만들지 않습니다.
UI의 안전시설 버튼 하나가 경찰/119/병원을 제어해도 DB category는 그대로 유지합니다.

Git clone만으로 기존 데이터를 얻을 수 없습니다. 별도 적재/백업 복원이 필요합니다.
로컬 .env 또는 VM private/service-env의 값 변경은 기존 DB 암호를 자동 변경하지 않습니다.
VM의 DB 볼륨은 safealley-deploy_postgis_data이며, 앱 업데이트는 기존 데이터를 복원/초기화하지 않습니다.
사용자 식별/선택 기록은 로그인 인증을 대체하지 않습니다.
테스트는 전용 fixture·롤백을 사용하며 운영 DB에 실행하지 않습니다.

[데이터 운영](data-pipeline.md), [건물 원천/매핑](building-data.md).
