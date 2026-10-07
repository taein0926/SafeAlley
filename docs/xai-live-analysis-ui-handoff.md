# XAI 처리 과정·실시간 분석 UI 연동 범위

기준: origin/main 8e836a4. 기존 처리 과정 스트리밍과 지도 위 경로 카드(80f260a)는 이미 main에 포함되어 있다. 이 브랜치는 그 위에 검색 아래 영역의 현재 화면과 입력 중 실시간 분석 기본 연동을 추가한다.

## 포함

- 검색 아래 처리 과정 전체: 'AI가 길을 찾고 있어요' 제목, 실제 진행 이벤트·측정값·최종 설명.
- 진행 중 말하는 입술 SVG, 완료 시 정지, 모션 줄이기 설정 지원.
- 질문·검색 버튼 고정 유지, 완료 후 처리 내용 맨 아래 스크롤, 이후 수동 스크롤 위치 유지.
- 계산값 펼침 표와 해당 화면의 부가 안내 문구 제거.
- 입력 중 7개 조건 카드, 최신 전체 문맥 전달, 늦은 응답 무시, 입력 묶기, 이전 카드 유지, 검색 시작 시 미리보기 예약 중단.
- Jev 기본 API 연결 및 7개 실제 반영 데이터의 additive 응답 필드. 기존 recommendation_factors는 유지한다.

## 의도적으로 제외

- Qwen 프롬프트·자연어 판정 보정 변경.
- Jev/Qwen 최종 문장 일치 검사, 확인 토큰·조건 확인 팝업.
- 낮은 신뢰도의 긍정을 원문 검산으로 적용하는 최근 개선.
- 출발 시각 누락 시 가로등 조건 확인 및 시간 카드 의미 변경.
- 경로 생성·추천 점수·주간 정책·성능 최적화 변경.
- 실제 API 키, .env, DB/볼륨, 원본 데이터, 실험 결과·화면 캡처.

원본 개발 작업 경로에는 위 제외 변경을 그대로 보존한다. UI 전달본의 기본 판정은 별도의 품질 개선본과 다를 수 있다. 담당자는 화면 배치·색상·입술/카드 아이콘을 바꾸되 API와 이벤트 계약을 유지하면 된다.

## 담당자 연동 지점

| 용도 | 위치 |
| --- | --- |
| 처리 과정 화면/입술 | frontend/src/components/RouteProgressPanel.tsx |
| 처리 과정의 문구·이벤트 읽기 | frontend/src/routeProgress.ts (main 기존 기능) |
| 고정 입력·완료 스크롤·연동 | frontend/src/App.tsx |
| 카드 표현 | frontend/src/components/RecommendationIcons.tsx, frontend/src/routeCards.css |
| API 요청/입력 묶기 | frontend/src/liveIntentPreview.ts |
| React 상태 훅 | frontend/src/useLiveIntentPreview.ts |
| 7개 항목·상태 데이터 | frontend/src/conditionCards.ts |
| 실시간 API | backend/app/api/intent_preview.py |
| Jev 연결 | backend/app/services/jev_preview_service.py |
| 검색 결과 7개 카드 정보 | backend/app/services/condition_cards.py |

처리 과정은 /api/agent/query/stream의 NDJSON stage/interpreted/resolved/route_progress/result/error를 표시한다. LLM의 비공개 사고 과정이 아니다.

## API 계약

GET /api/agent/intent-preview/status는 enabled/configured/available만 반환한다. 키는 반환하지 않는다.

POST /api/agent/intent-preview의 입력은 {"query":"전체 입력 문장"}이다. 반환 conditions는 distance/safety/streetlight/cctv/stairs/crossing/time 7개이며 state는 analyzing/applied/not_applied다. 원래 choice(judgment)·confidence·direction·period도 제공한다.

main 통합 UI는 기존 검색창 너비·아이콘 전환·예시 검색을 유지한다. 카드의 표시 순서는 첫 줄 distance/streetlight/cctv/safety, 둘째 줄 stairs/crossing/time이다. 건널목 카드는 '건널목 회피'로 표시한다. 적용/미적용 표시는 색과 테두리로 구분하고 별도 상태 텍스트 및 하단 안내는 렌더링하지 않는다. 상태는 접근성 이름에 유지하며, 연결 오류는 카드 위의 짧은 상태와 툴팁으로 확인할 수 있다.

최종 검색 결과의 recommendation_conditions는 경로에 반영된 조건을 표시하는 데이터다. 입력 중 요청 인식과 적용 정책은 서로 다른 단계다. 이 브랜치의 시간 카드 등 기본 메타데이터 투영은 기존 정책을 유지하며 최근 의미 보정은 별도 작업이다.

## 유료 기능 활성화와 개인정보

기본은 JEV_PREVIEW_ENABLED=false이고 실제 키는 포함하지 않는다. 담당자가 자신의 비공개 .env에 TYPESAFE_API_KEY를 설정하고 JEV_PREVIEW_ENABLED=true로 명시적으로 활성화해야 동작한다.

활성화하면 입력 중 전체 문장(장소명·시간·조건 포함)이 TypeSafe https://api.typesafe.ai/v1/systemone으로 전송된다. 문장에 민감한 주소나 개인 정보가 있으면 함께 전송될 수 있으므로 사용 대상에게 안내하고 허용된 입력만 사용해야 한다. 유료 API이며 누적 호출 횟수 제한은 없다. 입력 대기·최소 간격·60초 동일 문장 캐시는 유지한다.

이 브랜치는 검색 버튼을 눌렀다는 이유로 추가 Jev 최종 검사를 호출하지 않는다. Qwen 최종 요청 해석과 기존 경로 계산은 main의 동작 그대로다.

## 테스트

백엔드 pytest tests/unit, 프런트 npm test 및 npm run build를 사용한다. 유료 모델 정확도 시험이 아닌 계약·UI 회귀 검사다.

frontend/tests/route-progress-ui.e2e.cjs와 live-intent-retention.e2e.cjs는 모델 응답을 모의해 유료 호출 없이 화면·입술·스크롤·기존 카드 유지 동작을 확인한다. E2E_BASE_URL을 지정하면 별도 검증 서버에서 실행할 수 있다. 첫 스크립트의 히트맵 검사는 로컬 map_tiles 자료가 필요하다. 이 브랜치에 DB나 타일 볼륨은 포함하지 않는다.

2026-10-07 전달본 검증: 백엔드 단위 테스트 263개, 프런트 140개, 두 Docker 빌드 통과. 별도 검증 화면에서 입술 움직임/완료 정지/모션 줄이기, 입력 영역 고정, 완료 후 맨 아래 스크롤, 수동 스크롤 유지, 실시간 카드 유지/철회/질문 초기화를 확인했다. 브라우저 검증의 유료 호출은 0회다. 원래 개발 중인 3002 앱은 변경하지 않았다.
