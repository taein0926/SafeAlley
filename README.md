# SafeAlley

인천광역시 미추홀구를 대상으로 하는 **Digital Twin 기반 안전한 골목 탐색 서비스**의 MVP입니다.

현재 MVP는 OpenStreetMap 보행 도로와 공식 건물 공간정보에 더해, 가로등·방범 CCTV·안전시설 접근성의 상대 점수를 독립적으로 저장하고 종합 안전도를 표시하는 구조를 제공합니다. CCTV와 AI-ready 안전시설은 원천 파일/인증 설정 후 배치 적재합니다.

## 현재 구성

```text
Browser
  -> OpenStreetMap tile server (direct HTTPS tile request)
  -> React frontend (Nginx, localhost:3000)
     -> /api/* reverse proxy
     -> FastAPI backend (localhost:8000)
     -> PostgreSQL + PostGIS
```

외부 데이터 수집과 전처리는 상시 서비스와 분리된 `data_pipeline/`에서 배치로 수행할 예정입니다.

## 요구 사항

- Docker Desktop 또는 Docker Engine
- Docker Compose v2 이상

## 실행

먼저 예제 환경변수를 복사합니다.

PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

`.env`의 `POSTGRES_PASSWORD`를 로컬 환경에 맞게 변경한 뒤 실행합니다.

```bash
docker compose up --build
```

다른 터미널에서 OSM 수집부터 적재까지 실행합니다. `pipeline`은 이 명령이 실행되는 동안에만 생성되는 일회성 컨테이너입니다.

```bash
docker compose --profile tools run --build --rm pipeline run-osm
```

접속 주소:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- Road GeoJSON: http://localhost:8000/api/roads
- Streetlight safety GeoJSON: http://localhost:8000/api/safety/roads?source=osm
- Streetlight Point GeoJSON: http://localhost:8000/api/streetlights?source=michuhol-public-data
- Safety CCTV GeoJSON: http://localhost:8000/api/cctvs?source=data-go-kr-15096428
- Help Point GeoJSON: http://localhost:8000/api/help-points?source=ai-ready-help-points
- Building GeoJSON: http://localhost:8000/api/buildings?source=molit-gis-building
- Shortest route: `POST http://localhost:8000/api/routes/shortest`
- Safe route: `POST http://localhost:8000/api/routes/safe`
- FastAPI API 문서: http://localhost:8000/docs

종료:

```bash
docker compose down
```

DB 데이터까지 초기화해야 할 때만 다음 명령을 사용합니다. 이 명령은 로컬 DB 볼륨을 삭제합니다.

```bash
docker compose down --volumes
```

## Health 응답

`GET /health`는 API 프로세스 상태뿐 아니라 실제 DB 연결과 PostGIS extension을 확인합니다.

정상 응답 예시:

```json
{
  "status": "ok",
  "service": "backend",
  "database": {
    "status": "ok",
    "name": "safealley",
    "postgis_version": "3.x"
  }
}
```

DB 또는 PostGIS 확인이 실패하면 HTTP 503을 반환합니다.

## Road GeoJSON

```http
GET /api/roads
GET /api/roads?bbox=126.678,37.460,126.684,37.465
GET /api/roads?source=osm&bbox=126.678,37.460,126.684,37.465
```

응답은 `FeatureCollection`이며 geometry 좌표는 `EPSG:4326`입니다. DB에는 `EPSG:5179`로 저장됩니다.

## Building GeoJSON

```http
GET /api/buildings?source=molit-gis-building
GET /api/buildings?source=molit-gis-building&bbox=126.63,37.42,126.72,37.49
```

건물은 PostGIS에서 bbox 공간 인덱스로 필터링한 뒤 `EPSG:4326` GeoJSON `MultiPolygon`으로 반환됩니다. 원본 Polygon과 MultiPolygon은 적재 시 모두 지원하며, 실제 높이가 있을 때만 Cesium에서 3D extrusion을 사용합니다.

현재 로컬 개발 DB에는 사용자가 제공한 국토교통부 `AL_D010_28_20260909.shp`에서 미추홀구 코드 `28177`로 추출한 38,543동이 `source=molit-gis-building`으로 적재됩니다. 원본 파일은 Git에서 제외되므로 새 환경에서는 `docs/building-data.md`의 명령으로 다시 적재해야 합니다.

## 경로 API

```http
POST /api/routes/shortest
Content-Type: application/json

{
  "start": {"latitude": 37.4608, "longitude": 126.6790},
  "end": {"latitude": 37.4623, "longitude": 126.6830},
  "source": "osm"
}
```

같은 요청 body를 `POST /api/routes/safe`에도 사용할 수 있습니다. 두 응답은 동일한 구조이며 `route_type`, `total_distance`, `average_safety_score`, `total_cost`, GeoJSON `geometry`, segment별 안전도와 cost 내역을 포함합니다. `total_distance`와 호환 필드 `total_distance_m`의 단위는 m입니다.

입력 좌표에서 가장 가까운 그래프 노드를 찾으며 도로 graph에서 너무 먼 좌표는 `ROUTE_SNAP_MAX_DISTANCE_M` 기준으로 거부합니다.

## Structured Output과 Tool Router

`POST /api/agent/execute`는 LLM 또는 규칙 Parser가 만든 JSON을 Pydantic으로 검증한 뒤, 명시적으로 등록된 GIS Tool만 실행합니다. 이 엔드포인트가 자연어를 직접 해석하거나 SQL을 실행하지는 않습니다.

```http
POST /api/agent/execute
Content-Type: application/json

{
  "tool": "rank_routes",
  "arguments": {
    "origin": {"latitude": 37.4608, "longitude": 126.6790},
    "destination": {"latitude": 37.4623, "longitude": 126.6830},
    "departure_time": "22:00:00",
    "profile": "pedestrian",
    "source": "osm",
    "preferences": [
      {"factor": "distance_m", "direction": "minimize", "weight": 1},
      {"factor": "streetlight_score", "direction": "maximize", "weight": 3}
    ]
  }
}
```

현재 검증된 평가 지표는 `distance_m`, `safety_score`, `streetlight_score`, `cctv_score`입니다. `population_score`는 실제 유동인구 데이터가 적재되기 전까지 지원 지표로 노출하지 않습니다. Router는 경로 후보 생성과 지표 기반 순위 평가를 분리하며, 후보마다 요청 지표가 모두 존재할 때만 점수를 계산합니다. 등록됐더라도 데이터가 없는 지표와 `crosswalk_count`, `stairs`, `slope`, `police_accessibility` 같은 미등록 조건은 다른 값이나 0점으로 대체하지 않고 `unsupported_preferences`로 반환합니다. 모든 요청 조건이 미지원이면 후보는 반환하되 최종 경로는 선택하지 않습니다.

`departure_time`이 20:00 이상 또는 06:00 미만이면 야간 정책을 적용합니다. 사용자가 조건을 생략한 야간 요청은 거리와 함께 안전도·가로등·CCTV를 기본 평가하고, 사용자가 지정한 안전 관련 조건에도 야간 가중치를 적용합니다. 주간에 조건을 생략하면 최단거리를 기본값으로 사용합니다. 이는 실시간 유동인구나 운영 여부를 추정하는 기능이 아니라 입력 시각에 따른 명시적 경로 평가 정책입니다.

Tool 이름은 allowlist로 제한되고, 추가 JSON 필드와 임의 Tool 이름은 HTTP 422로 거부됩니다. 지표를 확장할 때는 Tool을 새로 늘리는 대신 `backend/app/services/route_metrics.py`의 registry에 검증된 계산 함수를 등록합니다.

## 가로등 기반 상대 안전지표

원본 `data_pipeline/raw/streetlights/인천광역시 미추홀구_가로등_20240806.csv`는 CP949, WGS84 좌표의 5,313개 가로등입니다. 원본과 처리 산출물은 Git에서 제외됩니다. 전체 파이프라인은 다음 명령으로 다시 실행합니다.

```bash
docker compose --profile tools run --build --rm pipeline run-streetlight-safety \
  --source michuhol-public-data --road-source osm --source-encoding cp949
```

분석은 원본 OSM 그래프를 변경하지 않고 별도 `road_safety_segments`에 20m 이하 구간을 생성합니다. DB 계산 좌표계는 EPSG:5179이며 API GeoJSON은 EPSG:4326입니다.

```text
distance_score = 100 * (1 - percentile_rank(nearest_light_distance_m))
density_score  = 100 * percentile_rank(light_density)
gap_score      = 100 * (1 - percentile_rank(dark_gap_proxy_m))
safety_score   = distance_score * 0.4 + density_score * 0.3 + gap_score * 0.3
```

`dark_gap_proxy_m`는 5m 간격 표본점 중 최근접 가로등 거리가 가장 큰 값입니다. 밀도 계산은 평행도로 혼입을 줄이기 위해 가로등을 먼저 가장 가까운 원본 도로에 매칭합니다. 30m 반경과 점수 가중치는 `.env`의 `STREETLIGHT_*` 설정으로 변경합니다.

이 점수는 국가 공식 안전점수가 아니라 **미추홀구 가로등 공간 분포 내 상대 순위로 만든 프로젝트 자체의 조명 접근성 지표**입니다.

## CCTV·AI-ready 안전시설·종합 안전도

CCTV 원천은 공공데이터포털 데이터 ID `15096428`인 `인천광역시 미추홀구 CCTV관리대장목록`입니다. `.env`의 `DATA_GO_KR_CCTV_API_URL`에는 인증된 공식 활용신청 화면에 표시된 요청 URL을, `DATA_GO_KR_SERVICE_KEY`에는 발급받은 키를 넣습니다. 저장소에는 임의 endpoint나 키를 포함하지 않습니다.

먼저 실제 설치목적 값과 건수를 확인한 뒤 그 값만 `SAFETY_CCTV_PURPOSES`에 쉼표로 지정합니다.

```bash
docker compose --profile tools run --rm pipeline collect-cctvs
docker compose --profile tools run --rm pipeline preprocess-cctvs
docker compose --profile tools run --rm pipeline load-cctvs
```

AI-ready 파일은 다음 위치에 그대로 둡니다. CSV 재병합·geocoding·새 GeoJSON 생성은 하지 않습니다.

```text
data_pipeline/raw/help_points/help_points_michuhol_routing_ready.geojson
```

```bash
docker compose --profile tools run --rm pipeline load-help-points
docker compose --profile tools run --rm pipeline analyze-safety-components
```

공간 계산은 EPSG:5179(m), API GeoJSON은 EPSG:4326입니다. CCTV 점수는 최근접 거리·30m 밀도·5m 표본 공백 대리값의 상대 순위이고, Help Point 점수는 최근접 유효 Point 거리의 상대 순위입니다.

```text
cctv_score = cctv_distance_score * 0.4
           + cctv_density_score  * 0.3
           + cctv_gap_score      * 0.3

help_point_score = 100 * (1 - percentile_rank(nearest_help_point_distance_m))

safety_score = streetlight_score * 0.4
             + cctv_score        * 0.4
             + help_point_score  * 0.2

risk = (100 - safety_score) / 100
safe_cost = distance_m * distance_weight
          + distance_m * risk * risk_weight
```

가중치는 `.env`의 다음 항목에서 변경합니다.

- `SAFETY_STREETLIGHT_WEIGHT`, `SAFETY_CCTV_WEIGHT`, `SAFETY_HELP_POINT_WEIGHT`
- `SAFE_ROUTE_DISTANCE_WEIGHT`, `SAFE_ROUTE_RISK_WEIGHT`

안전도 구성 가중치를 변경한 뒤에는 pipeline을 다시 실행하여 DB의 `safety_score`를 갱신해야 합니다. 경로 cost 가중치는 backend 재시작 후 바로 적용됩니다.

가로등 분석 실행 전 `OSM_SAFETY_SCORE_MODE=demo`는 PT용 임시값을 생성합니다. 분석 실행 후에는 파생 구간 점수의 길이 가중 평균이 원본 도로의 `streetlight_score`와 `safety_score`에 반영되어 안전 경로 탐색에서도 사용됩니다.

테스트 실행:

```bash
docker compose exec backend pytest -q
```

## 디렉터리

- `frontend/`: React 및 CesiumJS UI
- `backend/`: FastAPI와 PostGIS 조회 API
- `data_pipeline/`: 외부 데이터 수집·전처리·적재 배치
- `database/`: PostGIS 최초 초기화 SQL
- `docs/`: 아키텍처와 데이터 출처 문서

## OSM 데이터 파이프라인

```text
Overpass API
  -> data_pipeline/raw/osm/michuhol_roads.json
  -> 미추홀구 area 및 보행 가능 highway 필터
  -> OSM way를 연속 node-to-node edge로 분할
  -> data_pipeline/processed/osm/road_segments.geojson
  -> EPSG:5179 변환 및 PostGIS road_segments 적재
```

`raw/`와 `processed/` 산출물은 Git에서 제외됩니다. OSM 재적재는 하나의 트랜잭션에서 `source='osm'` 행을 교체합니다. 상세 명령과 필터 기준은 `data_pipeline/README.md`를 참고하세요.

OSM 데이터는 ODbL 조건으로 제공됩니다. 화면과 `NOTICE.md`에 OpenStreetMap attribution을 포함합니다.

## 지도 레이어 요청 구조

```text
tile.openstreetmap.org --direct--> Browser/CesiumJS

PostGIS road_segments        -> FastAPI /api/roads ---------+
PostGIS road_safety_segments -> FastAPI /api/safety/roads --+
PostGIS streetlights         -> FastAPI /api/streetlights ---+-> Browser/CesiumJS overlay
PostGIS buildings            -> FastAPI /api/buildings ------+
PostGIS cctvs                -> FastAPI /api/cctvs -----------+
PostGIS help_points          -> FastAPI /api/help-points -----+
```

OSM 타일은 FastAPI나 Nginx의 `/api` 프록시를 거치지 않습니다. 공용 OSM 타일은 개발·PT 수준의 대화형 지도에만 사용하고, 서비스 트래픽이 커지면 OSM Tile Usage Policy에 맞는 별도 제공자를 선택해야 합니다.

현재 CCTV 설치목적별 실제 건수와 Help Point category별 실제 건수는 원천 접근 설정/파일이 없으므로 문서에 임의로 기입하지 않습니다. 각 배치 명령이 실제 통계를 출력합니다.
---

<details>
<summary>GitLab Initial commit README 안내문 보존</summary>



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

* [Create](https://docs.gitlab.com/user/project/repository/web_editor/#create-a-file) or [upload](https://docs.gitlab.com/user/project/repository/web_editor/#upload-a-file) files
* [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin http://192.168.0.231/pilot2/safealley.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

* [Set up project integrations](http://192.168.0.231/pilot2/safealley/-/settings/integrations)

## Collaborate with your team

* [Invite team members and collaborators](https://docs.gitlab.com/user/project/members/)
* [Create a new merge request](https://docs.gitlab.com/user/project/merge_requests/creating_merge_requests/)
* [Automatically close issues from merge requests](https://docs.gitlab.com/user/project/issues/managing_issues/#closing-issues-automatically)
* [Enable merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)
* [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

* [Get started with GitLab CI/CD](https://docs.gitlab.com/ci/quick_start/)
* [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/user/application_security/sast/)
* [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/topics/autodevops/requirements/)
* [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/user/clusters/agent/)
* [Set up protected environments](https://docs.gitlab.com/ci/environments/protected_environments/)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
</details>
