# 미추홀구 보행 데이터와 검증

## 자료와 한계

| 자료 | 사용 | 기준일·범위 | 한계 |
| --- | --- | --- | --- |
| [인천시 도로시설물 3차원 POI](https://www.data.go.kr/data/15111545/fileData.do) | 공식 횡단보도 참조 점 839건, 가로등 점 3,884건 | 2022-10-31, 미추홀구 | 2차선 이상 도로 중심. 횡단보도 근접은 실제 횡단의 증거가 아니며, 가로등의 현재 점등·실제 조도를 보증하지 않음 |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | 보행 경로망, 횡단보도 노드·way, 계단·보도 태그 | 수집 시점의 OSM | 누락·오표기 가능. ODbL 출처 표시 필요 |
| [국토지리정보원 공개DEM](https://www.data.go.kr/data/15059920/fileData.do) | 2025년 인천 37611 도엽의 원본을 검증용으로 보관 | EPSG:5179, 90m 격자 | 보행로 경사 산출 기준(최대 10m 격자)에 맞지 않아 적재·경로 평가에 사용하지 않음 |

인천시 POI 원본은 `data_pipeline/raw/public_pedestrian/incheon_road_facilities_3d_poi_20221031.zip`에 보관하고 Git에서 제외한다. 원본은 EPSG:32652, DB와 거리 계산은 EPSG:5179, API·GeoJSON은 EPSG:4326을 사용한다. 원본 3D 점의 Z값은 시설물 높이일 수 있어 도로 경사로 사용하지 않는다. 공공데이터포털의 표시 이용허락은 “이용허락범위 제한 없음”이다.

## 공식 횡단보도 적재

```powershell
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose --profile tools run --rm pipeline preprocess-public-crosswalks
docker compose --profile tools run --rm pipeline load-public-crosswalks
```

전처리는 `시설물명칭=횡단보도`와 `시군구명=미추홀구`만 선별한다. 839건은 별도 `public_crosswalks` 테이블에 보존한다. 원본 2022년 자료와 현재 OSM의 시간 차이, 점과 보행 네트워크의 위치 차이 때문에 경로의 `crosswalk_count`에 자동 합산하지 않는다.

공식 점과 OSM에서 **이미 횡단보도로 태그된** 노드 또는 `footway=crossing` way의 거리가 8m 이내일 때만 출처 ID를 도로 속성 `official_crosswalk_source_ids`에 연결한다. 일반 도로 엣지의 중간에 점이 가깝다는 이유만으로 연결하지 않는다. 연결은 출처 대조용이며 신규 횡단 가능 엣지를 만들거나 `crosswalk_count`를 증가시키지 않는다. 도로망을 다시 적재한 경우 아래 연결 명령을 재실행한다.

```powershell
docker compose --profile tools run --rm pipeline link-public-crosswalks
```

2026-09-21 실제 DB 재실행: 공식 839점 중 25점이 OSM 횡단 노드/way와 연결됐고, 814점은 미연결이다. 연결된 엣지 중 횡단 태그가 없는 경우는 0건이었다. 미연결 점은 누락·좌표 오차·도로망 변화 등 원인을 판별하기 전까지 경로 집계에서 제외한다. 이 연결 자체도 현장에서 횡단 가능함을 증명하지 않는다.

## 공식 가로등 적재·분석

같은 원본에서 `시설물명칭=가로등`과 `시군구명=미추홀구`를 선별한다. 기존 가로등 소스는 덮어쓰지 않고 `incheon-road-poi-2022` 출처로 적재한다.

```powershell
docker compose --profile tools run --rm pipeline preprocess-public-streetlights
docker compose --profile tools run --rm pipeline load-public-streetlights
docker compose --profile tools run --rm pipeline analyze-streetlights --source incheon-road-poi-2022
docker compose --profile tools run --rm pipeline analyze-safety-components `
  --cctv-source mois-cctv-standard `
  --help-point-source official-help-points
```

마지막 명령은 가로등 분석 뒤 CCTV·도움시설 구성점수를 재계산해 기존 종합 지표를 복구한다. 이 자료는 현재의 점등 여부·밝기 실측치가 아니라 시설물 위치다. 2차선 미만 골목의 가로등은 빠질 수 있으므로 0점이나 어둠으로 단정하지 않는다.

## 지형 경사

공식 DEM(가급적 5m, 최대 10m)을 `data_pipeline/raw/elevation/`에 둔다. GeoTIFF 외에도 GDAL/Rasterio가 읽는 HFA IMG 원본을 직접 사용할 수 있다. CRS와 표고값이 있어야 하며 출처·기준일·라이선스를 명시한다. 현재 확보한 공식 공개DEM은 90m 격자이므로 DB의 경사 적재율은 여전히 0%다. 합성 5m DEM으로 계산 로직만 테스트했다.

2026-09-21 [국토정보플랫폼 국토정보맵](https://map.ngii.go.kr/)의 주안역 주변 `공개DEM` 2025년 `인천 37611` 도엽 ZIP을 사용자 다운로드 폴더에서 전달받았다. 원본 ZIP과 HFA IMG를 `data_pipeline/raw/elevation/`에 보관한다(Git 제외). 원본 ZIP SHA-256은 `51837C32035BBAD848E8EB91D4C836F67042016CE9DB612FC6D6FB7F920F12F0`이다. Rasterio로 확인한 실제 격자 크기는 **90m**, CRS는 **EPSG:5179**, 크기는 **255×316 픽셀**이다. `calculate_road_slopes`에 이 파일을 입력하면 `DEM cell size 90 m is too coarse ... maximum is 10 m`로 거절된다. 재보간으로 픽셀 수만 늘려도 원본의 공간 정확도가 높아지지 않으므로 경로 경사 DB에 적재하지 않는다. 더 고해상도의 적법하게 이용 가능한 DEM 또는 현장 측량 자료가 확보될 때까지 경사 정보는 미측정으로 유지한다.

2026-09-21 [국토정보플랫폼 민원예약](https://map.ngii.go.kr/ic/enquiry/enquiryList.do)에 `인천 미추홀구 5m·10m DEM 제공 및 활용 가능 여부 문의`를 접수했다(게시글 ID 8314, 상태: 접수). 미추홀구 포함 여부·제작연도, 개인·민간 PoC 신청 자격·절차·비용, 내부 DB 적재 및 경로 분석 결과 공개 허용 범위, 공식 대체 자료를 질문했다. 기관 답변 전에는 5m·10m DEM의 제공·이용 가능성을 확정하지 않는다. [국토환경성평가지도 경사도 분석](https://ecvam.neins.go.kr/board/faq/faqView.do?board_seq=270&pageIndex=1)은 5m DEM 기반이지만 참고용 결과이며 원본 DEM 파일과 구별한다. [필지별 5m급 경사도 정보](https://www.bigdata-realestate.kr/rebpp/usr/prd/prdInfoDetail.do?req_productId=23)도 필지 단위 평균·최저·최고값이므로 보행로 엣지 경사를 대체하지 않는다.

```powershell
docker compose --profile tools run --rm pipeline calculate-road-slopes `
  --input /pipeline/raw/elevation/michuhol_dem.img `
  --source-dataset "공식 DEM 자료명" `
  --source-url "공식 데이터셋 URL" `
  --source-date "YYYY-MM-DD" `
  --source-license "이용허락 명칭"
docker compose --profile tools run --rm pipeline load-road-slopes
```

도로 엣지 양 끝의 DEM 표고를 bilinear 보간하고, 표고차 절댓값/측지거리×100으로 지형 경사율을 추정한다. 엣지가 셀 크기의 2배보다 짧거나 NoData이면 미측정으로 둔다. 기존 도로·안전도 점수는 덮어쓰지 않는다. 모든 엣지의 경사가 있는 경로에서만 `max_slope_percent`를 표시·순위화하며, 일부만 있으면 `데이터 부족`으로 둔다. 이는 현장 보도면·경사로의 실측 경사도가 아니며 휠체어 통행 가능 여부를 보증하지 않는다.

## 경로 품질과 자연어 회귀

```powershell
docker compose --profile tools run --rm pipeline audit-road-network
docker compose --profile tools run --rm pipeline audit-road-network `
  --field-audit-output /pipeline/processed/audit/major_road_field_check.geojson `
  --crosswalk-audit-output /pipeline/processed/audit/route_crosswalk_review.geojson
docker compose --profile tools run --rm --entrypoint python pipeline -m pytest -q -k 'not postgis_composite_analysis'
docker compose exec backend python -m evals.evaluate_intent
```

경로망 감사는 `config/pedestrian_route_cases.json`의 3개 실제 출발·도착 좌표에 대해 그래프 연결, 스냅 거리, `motorway`·`foot=no` 통과 여부를 검증한다. 이것은 **현장 답사나 공식 보행로 확인을 대체하지 않는다.** `major_road_field_check.geojson`은 세 경로에 등장한 `major_road_fallback` 엣지를 중복 제거한다. `route_crosswalk_review.geojson`은 데모 경로 25m 이내 공식 횡단보도 점의 위치와, 경로 위·주변 OSM 횡단 노드/way와의 8m 이내 대응 상태를 기록한다. 점이 가깝기만 한 곳에 횡단 엣지를 자동 생성하지 않는다. 두 파일을 QGIS에서 열어 보도의 연속성, 합법적 횡단, 계단·장애물, 야간 시야를 사진·검수자·일시와 함께 기록한다. 모두 `unverified`로 시작하며 직접 확인 전에는 안전성을 주장하지 않는다. 자연어 평가 20문장은 출발지·도착지·시간·모든 조건의 factor와 방향을 비교한다. 미지원 조건은 다른 지표로 대체하지 않는다. `avoid`는 후보 중 해당 값이 0인 경로에만 적용하며, 그런 후보가 없으면 선택 경로를 제시하지 않는다.

2026-09-21 실행 기록: 경로망 3/3 연결, 금지 도로 0건, 출발·도착점 도로망 스냅 31~49m. 다만 각 경로에 보행 가능 여부가 현장에서 확인되지 않은 대로 대체 구간이 각각 5·10·7개, 중복 제거 시 14개 있다. 데모 경로 25m 이내 공식 횡단보도 점 22곳은 모두 연결 검토가 필요했고, 경로 위 또는 주변 OSM 횡단 노드/way 대응이 확인된 곳은 0곳이었다. API 최단경로도 3/3 응답했으나, 해당 경로의 횡단보도 집계는 0건이고 DEM 경사 측정률은 0%다. 공식 가로등 3,884건을 사용해 도로 16,471개·세부 구간 36,210개의 상대 가로등 지표를 재계산했다. 방범·어린이보호 CCTV 원본 3,100건은 저정밀 좌표 231개로 집계해 중복 밀도 과장을 제거했고, 도움시설 8건과 종합 분석을 다시 완료했다. 종합 점수 누락은 0건이다. CCTV 좌표 셀은 실제 설치점이 아니므로 정밀 경로 주변 CCTV를 보증하지 않는다. 따라서 이 결과를 보행 안전성 또는 무장애 경로 검증 완료로 해석하면 안 된다. 로컬 Qwen3:4b의 복합조건 구조화 회귀평가 결과는 아래 실행 로그를 기준으로 기록한다. 이는 구조화 정확도이며, 실제 경로의 현장 적합성 평가는 아니다.

후보 경로에 `major_road_fallback`이 남아 있으면 API는 그 구간의 `field_status=unverified`와 건수를 반환한다. 검증되지 않은 대로 구간이 없는 후보만 최종 선택 대상으로 삼는다. 모든 후보에 이 구간이 있으면 `selected_route=null`, `recommendation_status=field_review_required`로 응답하고 화면에는 현장 검토가 필요한 **경로 후보**로 표시한다. 후보를 지도에서 확인할 수는 있지만 안전 경로로 확정하거나 선택 기록을 저장하지 않는다. 이는 위험이 입증됐다는 뜻이 아니라 안전성을 확인하지 못했다는 뜻이다.
