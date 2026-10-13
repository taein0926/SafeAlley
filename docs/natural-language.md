# 문장 해석과 요구사항 미리보기

## 최종 검색

POST /api/agent/query/stream → Ollama structured output → Pydantic·의미 검증 →
공통 장소 resolver → 허용된 rank_routes → 실제 진행·최종 후보.
SQL·좌표를 모델이 임의 생성하도록 하지 않습니다.

출발/도착 역할·출발 시각·선호 방향을 확인하며 요청하지 않은 장소/시각/조건을 만들지 않습니다.
부정·허용·철회·뒤의 수정, 비교에서 제외한 조건, 한글 시각, 강한 avoid와 부드러운 minimize를
구분합니다. 제한된 원문 검산은 모델의 모든 새 표현을 이해하는 보장이 아닙니다.
형식·의미 실패는 최대 1회 보정 요청하며 연결 실패는 오류로 반환합니다.
다른 모델이나 임시 해석으로 조용히 성공 처리하지 않습니다.

자연어 검색은 explicit_only로 명시 요청 조건을 보존하고 과거 선택 선호를 몰래 섞지 않습니다.
계산 기본값과 화면에 사용자가 요청했다고 표시하는 조건은 구분합니다.
시각 미지정 시 계산의 현재 시간 정책이 사용돼도 특정 시각을 요청했다고 만들지 않습니다.
장소 문자열은 places → 지역 제한 GIS building → Nominatim의 공통 resolver를 사용합니다.

## 입력 중 미리보기(Jev)

입력 중 전체 문장은 별도 TypeSafe API로 전달될 수 있으므로 민감한 주소/개인정보 입력을 주의합니다.
JEV_PREVIEW_ENABLED=true와 서버 TYPESAFE_API_KEY가 모두 필요하며 기본은 비활성화입니다.
상태 API는 enabled/configured/available만 반환하고 키를 노출하지 않습니다.
이는 유료 외부 서비스이고 Ollama 문장 검색과는 별개입니다.

카드는 distance/streetlight/cctv/safety / stairs/crossing/bridge/time 순서입니다.
analyzing/applied/not_applied, direction/confidence/period/judgment를 보존합니다.
미완성 조건·낮은 신뢰도·철회는 실제 판단 정책으로 처리하며 다른 항목에서 육교를 추론하지 않습니다.
띄어쓰기 경계와 마지막 단어 idle 처리·요청 묶기·캐시·늦은 응답 무시를 사용합니다.
예시는 공백을 포함해 모든 글자를 55ms 간격으로 입력하며 공백에서 따로 멈추지 않습니다.
문장 입력 모드의 조건 카드는 빈 입력·검색 중·성공/실패 후에도 검색창에 유지하고 직접 설정에서는 숨깁니다. 빈 입력은 미선택 상태이며
분석 호출/로딩 표시가 없습니다. 검색을 시작하면 미리보기 요청을 멈추고 마지막 판단을 보존합니다.
검색 중/검색 완료 결과를 입력 미리보기로 덮어쓰지 않습니다.
육교 독립 라우팅 가중치는 아직 없으므로 인식과 경로 적용을 구분합니다.

## 평가

단위/계약/UI mock은 실제 모델 정확도 평가가 아닙니다.
backend/evals에는 문장·역할·시간·조건 방향·회피·추가/누락을 비교하는 평가 도구와
회귀 문장이 남아 있습니다. 테스트에 사용된 문장을 새 독립 성능으로 부르지 않습니다.
오래된 모델/DB/저정밀 CCTV 기반 경로 결과를 최신 정확도·안전 보장으로 사용하지 않습니다.

실제 모델 live 평가는 운영자의 외부 호출·부하 허용 범위에서 별도로 수행합니다.

```powershell
# 실행 모델/설정과 공간 DB를 먼저 확인합니다.
docker compose run --rm --no-deps backend python -m evals.evaluate_intent --set dev --quiet
docker compose run --rm --no-deps backend python -m evals.route_progress_smoke
```

코드 변경 후에는 backend 이미지를 갱신하거나 현재 소스를 연결해야 합니다.
평가 상세 옵션은 backend/evals/README.md와 각 --help를 따릅니다.
[캐시/처리](ai-search-performance.md), [UI](route-progress-floating-cards.md),
[전체 회귀 검증](testing.md), [AI 연결](ai-setup.md).
