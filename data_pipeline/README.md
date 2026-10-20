# 공간 데이터 파이프라인

외부 공간 데이터 수집·정제·좌표 변환·PostGIS 적재와 시설 지표 분석을 수행하는
독립 배치 영역이다. FastAPI 내부에 넣지 않으며 상시 웹 서버로 실행하지 않는다.

```text
collectors → raw → preprocess → processed → loaders → PostGIS → analysis
```

- `collectors/`: 확인된 원천 수집.
- `preprocess/`: 영역·보행 규칙·geometry·좌표·OSM metadata 정제.
- `loaders/`: 검증된 데이터의 DB 적재.
- `analysis/`: 시설 거리·밀도·공백 지표와 표시용 타일.
- `config/`: 실제 원본 컬럼 매핑.
- `raw/`, `processed/`: 원본·가공 데이터, Git 제외.

## 현재 원천

| 데이터 | 원본/처리 원칙 |
| --- | --- |
| 도로·계단·건널목 태그 | OSM Overpass snapshot, osm_tags 보존 |
| 건물 | MOLIT AL_D010_28_20260909 SHP, source=molit-gis-building |
| 가로등 | 제공된 미추홀구 CSV와 공식 도로시설 POI |
| CCTV | raw/cctvs/cctv_michuhol_ai_ready.geojson, 정밀 좌표 |
| 경찰·119·병원 | raw/help_points/help_points_michuhol_routing_ready.geojson |
| 보행 참조 | 확인된 육교·교차로 GeoJSON과 OSM 연결 정보 |
| 예보·일출/일몰 | 승인된 KMA/KASI API, 별도 weather 배치 |

소스 파일은 Git에 포함되지 않는다. 새 환경에서는 공식 원본 또는 승인된 백업을
준비해야 한다. 시설 위치와 지표는 실제 밝기·촬영 범위·안전을 뜻하지 않는다.
원본 CRS를 확인하고 처리 GeoJSON은 EPSG:4326, DB 공간 분석은 EPSG:5179로 관리한다.
건물의 높이·층수나 계단 태그에 없는 값은 임의 추정하지 않는다.

## 명령

아래 명령은 소스·원본이 있는 로컬 또는 별도 데이터 작업 환경의 저장소 루트에서 실행한다.
현재 VM의 고정 runtime 구성에는 pipeline/tools 서비스가 없으며, 앱 배포 도구는 공간 원본을
재적재하지 않는다. 운영 DB 갱신은 별도 승인·백업·작업 환경을 준비해야 한다.
현재 서버 업데이트와 데이터 구축을 혼용하지 않는다. [서버 배포](../deployment/README.md).
옵션 정본은 CLI 도움말이다.

```powershell
docker compose --profile tools run --rm pipeline --help
```

OSM 최초 구축은 [데이터 운영](../docs/data-pipeline.md)을 먼저 따른다.
`run-osm`/`load-osm`은 기존 source=osm 데이터를 교체한다.
.env.example의 `OSM_SAFETY_SCORE_MODE=demo`는 실제 시설 점수가 아닌
이전 PT용 설정이므로 기존 서비스에 무심코 재적재하지 않는다.
기존 DB의 갱신은 백업·metadata·dry run 검사를 갖춘 `loaders.osm_refresh`를 사용한다.

정밀 CCTV와 안전시설 원본을 준비한 경우:

```powershell
docker compose --profile tools run --rm pipeline load-cctvs
docker compose --profile tools run --rm pipeline load-help-points
docker compose --profile tools run --rm pipeline analyze-safety-components
```

로드·분석 명령은 DB를 수정한다. source·대상·백업을 확인한 뒤 필요한 명령만 실행한다.
가중치 변경은 재분석 후 저장 점수에 반영된다. 전체 흐름과 히트맵 생성 명령은
[데이터 운영](../docs/data-pipeline.md)을 참고한다.

## 관련 안내

- [건물 파일·좌표계·필드 매핑](../docs/building-data.md)
- [보행·시설 데이터 품질](../docs/pedestrian-data-quality.md)
- [건널목·육교 연결](../docs/intersection-routing.md)
- [날씨 배치](../docs/weather.md)
- [원천·라이선스](../NOTICE.md)
- [현재 테스트 실행](../docs/testing.md)

테스트는 현재 소스를 읽기 전용으로 연결해 실행한다. 통합 테스트는 로컬 테스트
DB만 사용하며 실제 원본이 필요한 skip은 통과와 구분한다.
