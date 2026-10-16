# 아키텍처

이 문서는 2026-10-16 확인한 VM 앱 배포본 `942c752`를 기준으로 작성했습니다. 이후 실제 배포 커밋과 비공개 설정은 서버에서 다시 확인합니다.

## 애플리케이션 경계

```text
브라우저
 ├─ OSM 타일 직접 HTTPS 요청
 └─ Nginx / React / CesiumJS
       └─ /api/* → FastAPI
             ├─ repository → PostgreSQL / PostGIS
             ├─ 승인된 SSH 터널 → GPU 서버 Ollama → 검색 문장 구조화
             ├─ 승인된 SSH 터널 → GPU 서버 Whisper → 음성 변환
             │                         └─ 연결 실패 시 backend CPU Whisper
             ├─ Jev / TypeSafe → 선택적 입력 중 해석
             └─ Nominatim → 지역 제한 장소 fallback / reverse

외부 원본 → data_pipeline: collectors → raw → preprocess → processed → loaders / analysis → DB
weather 배치 → KMA/KASI → DB 캐시
```

Frontend는 DB에 접근하지 않습니다. route는 요청/오류 처리, service는 업무 흐름,
repository는 공간 쿼리, services/routing은 탐색을 담당합니다.
모델이 그래프를 계산하거나 임의 SQL을 실행하지 않습니다.
배치 수집은 backend/app 내부에 넣지 않습니다.

브라우저 /api/health는 Nginx가 backend /health로 연결합니다.
NDJSON 검색 스트림은 proxy_buffering off로 실제 작업 진행을 전달합니다.

## 실행 서비스

| 서비스 | 역할 | 지속 데이터 |
| --- | --- | --- |
| frontend | Nginx + React/Cesium 정적 파일 | 빌드 |
| backend | FastAPI, 요청 내 그래프, GPU 음성 중계·CPU 대체 처리 | CPU 대체용 stt_models; map_tiles 읽기 |
| database | PostgreSQL 17 / PostGIS 3.5 | postgis_data |
| weather | 발표시각별 배치, 포트 없음 | DB 날씨 캐시 |
| pipeline | tools 프로필 일회성 적재·분석 | raw/processed; map_tiles 쓰기 |

Frontend/backend는 public, backend/database는 private internal 네트워크를 공유합니다.
배치 작업은 외부 수집/DB 적재를 위해 두 네트워크를 사용합니다.
로컬 루프백 포트: frontend 3000, backend 8000, DB 5432.

VM/GPU 방식은 루트 Compose + deployment/compose.vm.override.yml입니다.
VM에 앱/DB/weather를 두고 host gateway 11435(Ollama)·11436(Whisper)의 승인된 SSH 터널로 GPU 서버에 접속합니다.
2026-10-16 확인한 VM 모델은 `gemma4:26b`입니다. 저장소 VM override의 `qwen3.6:35b`는 설정하지 않았을 때의 템플릿 기본값입니다.
VM은 frontend 루프백 8080만 공개하고 backend/DB 포트는 제거합니다.
단일 GPU 서버 대안은 deployment/compose.yml이며 두 방식을 혼용하지 않습니다.

## 검색과 지도

- 문장: query/stream → Ollama structured output → 형식·의미 검사 → 공통 resolver → rank_routes.
- 직접 설정: 텍스트 위치만 places/resolve → 좌표·선호를 agent/execute → 같은 rank_routes.
- 지도 선택: 이미 있는 좌표를 직접 전달하고 reverse는 표시명에만 사용합니다.
- 장소: places 정규화/별칭/부분검색 → 지역 제한 GIS 건물 → 제한된 Nominatim.
- 입력 미리보기: 띄어쓰기 경계/마지막 단어 idle → Jev 조건 카드. 최종 경로 적용과 별개입니다.

전체 안전도 도로선은 초기 표시하지 않습니다. 시설/건물/계단·육교는 bbox·타일 캐시를 사용합니다.
높이가 있는 건물만 extrusion을 적용합니다. 경로는 segment ID 순서/geometry로 dedup합니다.
2D/3D는 사용자 선택을 유지하고 경로 camera fit은 패널이 가리는 공간을 고려합니다.

가로등 밀집도는 pipeline에서 등록 위치로 만든 PNG 타일을 backend가 제공하는 별도 overlay입니다.
OSM 배경 타일과 다르며 실제 조도나 경로 비용을 바꾸지 않습니다.

## 좌표·보안

DB 거리/버퍼: EPSG:5179(m). API/GeoJSON/bbox: EPSG:4326(longitude/latitude).
원본 SHP 좌표계는 metadata로 확인해 변환합니다.
비밀값은 .env, VITE_*에는 넣지 않습니다. 원본·DB·백업·타일·모델은 Git과 별도로 관리합니다.

상세: [라우팅](routing.md), [데이터](data-pipeline.md), [날씨](weather.md),
[배포](../deployment/README.md), [테스트](testing.md).
