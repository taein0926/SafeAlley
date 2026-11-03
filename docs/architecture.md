# 아키텍처

이 문서는 2026-10-29 PC 모델 전환 구성을 기준으로 합니다. 적용 소스는 VM의
`runtime/state.json`, 전달본 소스는 압축파일 내부 `release.json`으로 확인합니다.

## 애플리케이션 경계

구성도 원본은 [service-architecture.svg](assets/service-architecture.svg)입니다.
브라우저는 앱 서버에 접속하고, VM의 모델 요청은 비공개 SSH 역방향 터널을 통해 PC로 전달합니다.
PC의 Gemma E2B는 GPU, Whisper small과 Laya ONNX는 CPU에서 각각 실행합니다.

```text
브라우저
 ├─ OSM 타일 직접 HTTPS 요청
 └─ HTTPS 외부 :21802 → VM :8081 → Nginx :80(TLS) / React / CesiumJS
       └─ /api/* → FastAPI
             ├─ repository → PostgreSQL / PostGIS
             ├─ 전달기·SSH 역방향 터널 → PC Ollama Gemma E2B → 검색 문장 구조화
             ├─ 전달기·SSH 역방향 터널 → PC Whisper small CPU → 음성 변환
             ├─ 전달기·SSH 역방향 터널 → PC Laya ONNX CPU → 입력 중 조건 해석
             │                         └─ Jev / TypeSafe는 명시적 선택·복구용, 자동 대체 없음
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
| backend | FastAPI, 요청 내 그래프, PC 음성 중계 | map_tiles 읽기 |
| database | PostgreSQL 17 / PostGIS 3.5 | postgis_data |
| weather | 발표시각별 배치, 포트 없음 | DB 날씨 캐시 |
| pipeline (로컬/데이터 작업 환경) | tools 프로필 일회성 적재·분석, 현재 VM runtime에는 없음 | raw/processed; map_tiles 쓰기 |

Frontend/backend는 public, backend/database는 private internal 네트워크를 공유합니다.
배치 작업은 외부 수집/DB 적재를 위해 두 네트워크를 사용합니다.
로컬 루프백 포트: frontend 3000, backend 8000, DB 5432.

현재 VM의 네 컨테이너는 고정 `runtime/compose.json`에서 실행합니다. frontend는
`0.0.0.0:8081 → 80`에서 자체 서명 HTTPS를 제공하며 backend/DB 포트는 호스트에 공개하지 않습니다.
인증서·Nginx 설정은 `private/tls-f6b47f3/`, 서비스 환경변수는 `private/service-env/`입니다.
VM 전달기 포트 `11439/11440/18763`은 각각 PC의 Gemma/Whisper/Laya에 연결합니다.
PC의 연결 관리자가 SSH 역방향 터널을 유지하므로 PC 기동과 명시적 VM 연결이 필요합니다.
`STT_LOCAL_FALLBACK=false`로 PC 연결 실패 시 VM 모델 실행을 막습니다.

로컬은 루트 Compose와 `deployment/compose.pc-ai.yml`을 함께 사용합니다.
`pc-whisper`는 CPU INT8·2스레드와 `stt_models` 캐시, `pc-laya`는 ONNX FP32·2스레드와
별도 준비한 Laya 이미지/실행 폴더를 사용합니다. 모델 포트는 PC loopback에만 공개합니다.
설정·연결은 [PC AI 운영 안내](../deployment/pc_ai/README.md)를 따릅니다.

`packages/` 소스는 임시 폴더에서 빌드하고 제거합니다. 앱 갱신은 `runtime/update.py`를 사용하며
DB 데이터·PC 모델·인증서·터널을 압축본으로 대체하지 않습니다.
기존 VM/GPU override·단일 GPU Compose는 이전 설치 호환용으로 현재 PC 구성과 구분합니다.

## 검색과 지도

- 문장: query/stream → Ollama structured output → 형식·의미 검사 → 공통 resolver → rank_routes.
- 직접 설정: 텍스트 위치만 places/resolve → 좌표·선호를 agent/execute → 같은 rank_routes.
- 지도 선택: 이미 있는 좌표를 직접 전달하고 reverse는 표시명에만 사용합니다.
- 장소: places 정규화/별칭/부분검색 → 지역 제한 GIS 건물 → 제한된 Nominatim.
- 입력 미리보기: 띄어쓰기 경계/마지막 단어 idle → 선택한 Laya/Jev → FastAPI 보정 → 조건 카드. 최종 경로 적용과 별개입니다.

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
