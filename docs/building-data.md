# Building data source and import

확인일: 2026-09-15

## 확인된 내용

인천광역시 공식 i-Map은 2D·3D 지도, 건물정보 조합·분석과 3D 건물 속성 조회 기능을 서비스합니다.

- i-Map: https://imap.incheon.go.kr/
- i-Map 소개: https://imap.incheon.go.kr/sgp/por/intro.do

그러나 확인 시점에 i-Map 건물 전체를 배치 수집할 수 있는 공식 다운로드, 공개 API, WFS 명세와 이용조건은 확인하지 못했습니다. 웹 애플리케이션의 비공개 내부 요청을 분석하거나 scraping하지 않습니다.

공식 대체 원천으로 공공데이터포털의 국토교통부 `GIS건물통합정보`가 확인됐습니다. 건물 공간정보와 건축물대장 속성을 결합한 SHP 파일이며 공공저작물 출처표시 제1유형입니다.

- 데이터 상세: https://www.data.go.kr/data/15083092/fileData.do
- 기계 판독 메타데이터: https://www.data.go.kr/catalog/15083092/fileData.json
- A0~A28 필드 정의 확인 자료(국가교통DB 보고서, 표 5-15): https://www.ktdb.go.kr/DATA/pblcte/20250805093928585.pdf

i-Map이 이 데이터셋을 직접 사용한다는 근거는 확인하지 못했으므로, 국토교통부 파일을 사용하면 DB `source`를 `imap`이 아니라 `molit-gis-building` 등 실제 출처명으로 기록해야 합니다.

## 현재 제공·적재된 파일

사용자가 제공한 `AL_D010_28_20260909.zip`을 로컬 `data_pipeline/raw/buildings/molit_gis_building_20260909/`에 보존했습니다. `raw/`와 `processed/`는 Git에서 제외됩니다.

- 데이터셋: 국토교통부 GIS건물통합정보, 인천광역시
- 원본 SHP: `AL_D010_28_20260909.shp`
- 원본 건물 수: 309,863동
- 원본 CRS: EPSG:5186 (`Korea 2000 / Central Belt 2010`)
- DBF 인코딩: CP949 (`.cpg` 파일 없음)
- 미추홀구 필터: `A23` 원천시도시군구코드 = `28177`
- 처리 건물 수: 38,543동
- processed CRS: EPSG:4326
- PostGIS CRS/type: EPSG:5179 `MultiPolygon`
- DB source: `molit-gis-building`

이 파일은 i-Map 자체 배포 파일이라고 확인된 것이 아니므로 `source=imap`으로 표시하지 않습니다.

### 실제 필드 매핑

| API/DB 필드 | SHP 필드 | 원본 의미 |
|---|---|---|
| `building_id` | A1 | GIS건물통합식별번호 |
| `building_name` | A24 | 건물명 |
| `address` | A4 + A5 | 법정동명 + 지번 |
| `main_use` | A9 | 건축물용도명 |
| `building_area` | A12 | 건축물면적(㎡) |
| `total_floor_area` | A14 | 연면적(㎡) |
| `height_m` | A16 | 높이(m) |
| `floors` | A26 | 지상층수 |
| `source_updated_at` | A28 | 데이터생성변경일자 |

매핑 파일은 `data_pipeline/config/molit-gis-buildings-20260909.field-map.json`입니다. 전체 A0~A28 정의는 이 문서 아래 공식 데이터 표준 및 검증에 사용한 국토교통 DB 정의 자료를 기준으로 확인했습니다.

## 새 데이터 적재에 필요한 파일

다음 중 하나를 `data_pipeline/raw/buildings/` 아래에 둡니다.

- 공식 i-Map이 제공한 건물 SHP, GeoJSON 또는 GPKG
- 공공데이터포털에서 직접 내려받은 국토교통부 GIS건물통합정보 SHP

그리고 다음 중 하나가 필요합니다.

- 미추홀구 경계 Polygon/MultiPolygon 파일
- 원본 건물 파일 안의 구·군 구분 필드와 미추홀구 값
- 이미 미추홀구만 추출됐음을 확인할 수 있는 파일

SHP는 `.shp`, `.shx`, `.dbf`, `.prj` 등 구성 파일을 모두 같은 디렉터리에 보관합니다. 원본 CRS는 `.prj`/GPKG 메타데이터에서 읽으며 없으면 실행 시 `--source-crs`를 반드시 지정합니다.

필드명이 자동 인식되지 않으면 `data_pipeline/config/buildings.field-map.example.json`을 복사해 실제 컬럼명으로 수정합니다. 데이터 파일명, 공식 상세 URL, 라이선스, 기준일은 이 문서와 `NOTICE.md`에 추가한 후 적재합니다.

## source 규칙

- 공식 i-Map 배포 파일: `--source imap`
- 국토교통부 GIS건물통합정보: `--source molit-gis-building`
- 출처가 불명확한 파일: 적재하지 않음

건물 CLI에서 `--source`를 생략하면 현재 사용하는 `molit-gis-building`으로 처리합니다.
다른 공식 원천은 반드시 출처를 명시합니다. `load-buildings`는 가공 GeoJSON의 source와
교체 대상이 다르면 DB 연결 전에 중단합니다. 다른 출처로 표시된 가공 파일을 자동 변경하거나
기존 DB를 재분류하지 않으므로 실제 원천에 맞게 옵션을 지정하거나 다시 전처리해야 합니다.

프론트엔드의 기본 조회 source는 현재 적재 데이터와 동일한 `molit-gis-building`입니다. `VITE_BUILDING_SOURCE` 빌드 변수로 다른 공식 원천을 선택할 수 있으며, 그 값은 DB `buildings.source`와 같아야 합니다.
