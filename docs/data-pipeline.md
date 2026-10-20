# 데이터 구축과 갱신

collectors → raw 원본 → preprocess → processed 가공 → loaders → PostGIS → analysis.
모든 수집/정제/좌표 변환/적재는 data_pipeline에 두고 backend/app에 넣지 않습니다.
원천 URL·파일명·좌표계·기준일·라이선스를 기록하고 미확인 endpoint를 만들지 않습니다.
raw/processed/백업/타일은 Git에서 제외합니다. API는 4326, DB 거리 계산은 5179입니다.

이 문서의 Compose 명령은 소스를 clone하고 원본을 준비한 로컬/별도 데이터 작업 환경용입니다.
현재 VM의 `runtime/compose.json`에는 pipeline/tools 서비스와 raw/processed bind가 없습니다.
앱 업데이트는 기존 공간 DB·타일을 유지하며 재수집·재적재를 실행하지 않습니다.
운영 데이터 갱신은 별도 승인·백업·데이터 작업 환경을 준비해 진행하고, 서버에 루트 Compose를
그대로 적용하지 않습니다. [현재 VM 운영](../deployment/README.md)을 확인하세요.

## 원천

| 자료 | 입력 | 저장 |
| --- | --- | --- |
| 도로·계단·보행/건널목 태그 | OSM Overpass snapshot, osm_tags 보존 | road_segments |
| 건물 | 제공된 MOLIT AL_D010_28_20260909 SHP | buildings, source=molit-gis-building |
| 가로등 | 제공된 미추홀구 CSV, 인천 공식 도로시설 POI | streetlights |
| 정밀 CCTV | raw/cctvs/cctv_michuhol_ai_ready.geojson | cctvs |
| 경찰/119/병원 | raw/help_points/help_points_michuhol_routing_ready.geojson | help_points |
| 보행 참조 | 교차로/육교 GeoJSON + 실제 OSM 입체 연결 | pedestrian_references, road properties |
| 공식 횡단보도 | 별도 POI, 기존 OSM 횡단 태그와 대조 | public_crosswalks |
| 예보/출몰시각 | 승인된 KMA/KASI API | weather_forecasts/solar_times |

건물은 i-Map 수집 파일이라고 주장하지 않습니다.
[SHP 매핑](building-data.md), [라이선스](../NOTICE.md)를 확인하세요.
공식 POI가 가까워도 임의 도로 edge/횡단 연결을 만들지 않습니다.

## 빈 환경 최초 구축

```powershell
docker compose --profile tools run --rm --build pipeline run-osm
```

**source=osm 도로를 교체하는 명령이므로 기존 서비스 DB에는 무심코 실행하지 않습니다.**
.env.example과 Compose의 OSM_SAFETY_SCORE_MODE 기본값은 `uniform`입니다.
이는 도로마다 동일한 임시값(기본 50)을 넣는 것이지 실제 시설 안전도를 계산하는 것은 아닙니다.
실제 가로등·CCTV·안전시설을 적재한 뒤 아래 시설 분석을 실행해야 합니다.
과거 PT용 가상 점수 `demo`는 명시적인 시험에서만 선택합니다. 기존 .env와 DB를 자동 변경하지 않습니다.

## 기존 DB 갱신

loaders.osm_refresh는 snapshot과 같은 이름의 .meta.json 및 기존 검증된 pg_dump 백업을 요구하며
area 완전성·갑작스러운 도로 손실을 검사합니다.
먼저 dry run 하고 명시적 --apply 때만 ID 보존 upsert·보행 metadata·참조 연결·
가로등/CCTV/안전시설 재분석을 같은 트랜잭션에서 적용합니다.

```powershell
# 실제 제공 snapshot, 새 출력 경로와 승인된 백업으로 지정합니다.
docker compose --profile tools run --rm --no-deps --entrypoint python pipeline -m loaders.osm_refresh --input /pipeline/raw/osm/michuhol_roads.json --output /pipeline/processed/osm/refresh --backup /pipeline/raw/osm/pre-refresh.dump
# 검사/백업 확인 후 동일 인자에 --apply를 추가
```

41 Way/77 계단 구간 등의 과거 건수는 snapshot 기록이며 영구 고정 상수가 아닙니다.
`collectors/osm_pedestrian.py`와 `loaders/osm_pedestrian.py`의 `juan-v1` 수집·적재는
주안역 일부 영역을 다루던 과거 작업 도구입니다. 미추홀구 전체 최신화 명령이 아니며
현재 전체 갱신에는 위 `loaders.osm_refresh`를 사용합니다. 이전 metadata와의 호환을
위해 남긴 도구를 전체 수집으로 오인해 운영 DB에 실행하지 않습니다.
원본 재적재 후 계단 metadata·topology·source·안전도 coverage를 실제로 비교합니다.
이번 문서/테스트 정리는 도로를 새 수집하거나 DB를 갱신하는 작업이 아닙니다.

## 분석·표시 타일

```powershell
# 유효한 원본과 설정을 먼저 준비한 뒤 필요한 분석만 실행합니다.
docker compose --profile tools run --rm pipeline analyze-streetlights
docker compose --profile tools run --rm pipeline analyze-safety-components
docker compose --profile tools run --rm --no-deps --entrypoint python pipeline -m analysis.streetlight_heatmap
```

도로를 분석 구간으로 나눠 시설 거리·밀도·공백 proxy를 정규화하고 가중 종합 점수를 저장합니다.
원천/가중치 변경 후 재분석이 필요합니다.
밀집도 PNG는 map_tiles 볼륨에 저장하고 backend가 읽기 전용으로 제공합니다.
히트맵은 실제 조도가 아니며 경로 비용을 바꾸지 않습니다.

정밀 CCTV/안전시설은 기존 GeoJSON 로더를 사용합니다.
남아 있는 legacy CCTV API 옵션에 미확인 주소를 넣거나 정밀 좌표를 임의 값으로 대체하지 않습니다.
CLI 옵션: docker compose --profile tools run --rm pipeline --help.

weather는 공개 포트 없는 배치 실행기이며 [날씨 수집 주기](weather.md)를 따릅니다.
osm_display_roads 로더, /api/osm-roads, /api/crossings는 서비스에서 제거했습니다.
이전 migration 0016/테이블은 이력 호환을 위해 유지하고 실제 도로/선택 경로 횡단 안내는 보존합니다.
