# 아키텍처

이 문서는 2026-10-20 VM 운영 경로 전환 기준입니다. 적용 소스는 `runtime/state.json`,
원본 소스는 보관한 압축본의 `release.json`에서 확인합니다. 전환 기준 소스는 `f6b47f3`입니다.

## 애플리케이션 경계

```text
브라우저
 ├─ OSM 타일 직접 HTTPS 요청
 └─ HTTPS 외부 :21802 → VM :8081 → Nginx :80(TLS) / React / CesiumJS
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
| pipeline (로컬/데이터 작업 환경) | tools 프로필 일회성 적재·분석, 현재 VM runtime에는 없음 | raw/processed; map_tiles 쓰기 |

Frontend/backend는 public, backend/database는 private internal 네트워크를 공유합니다.
배치 작업은 외부 수집/DB 적재를 위해 두 네트워크를 사용합니다.
로컬 루프백 포트: frontend 3000, backend 8000, DB 5432.

VM/GPU 신규 템플릿은 루트 Compose와 VM 전용 override를 사용합니다.
VM에 앱/DB/weather를 두고 승인된 SSH 터널로 GPU 서버의 Ollama·Whisper에 접속합니다.
실제 모델·터널 주소와 템플릿 기본값의 차이는 [배포 안내](../deployment/README.md)를 확인합니다.
현재 VM의 네 컨테이너는 고정 `runtime/compose.json`에서 실행합니다. frontend는
`0.0.0.0:8081 → 80`에서 자체 서명 HTTPS를 제공하며 backend/DB 포트는 호스트에 공개하지 않습니다.
인증서·Nginx 설정은 `private/tls-f6b47f3/`, 서비스 환경변수는 `private/service-env/`입니다.
Ollama·Whisper SSH 터널은 VM의 systemd 서비스로 자동 실행하며 노트북 터널과 별개입니다.
`packages/`의 소스를 임시 폴더에서 빌드하고 제거합니다. 앱 갱신은 `runtime/update.py`를 사용하며
DB 데이터·GPU 서비스·인증서·터널을 새 압축본으로 대체하지 않습니다.
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
비밀값은 로컬 .env 또는 서버 private/service-env에서 관리하고 VITE_*에는 넣지 않습니다.
원본·DB·백업·타일·모델은 Git과 별도로 관리합니다.

상세: [라우팅](routing.md), [데이터](data-pipeline.md), [날씨](weather.md),
[배포](../deployment/README.md), [테스트](testing.md).
