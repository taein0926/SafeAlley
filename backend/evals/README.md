# 자연어 경로 요청 평가셋

evaluate_intent.py는 실제 Ollama 응답을 캐시 없이 받아 출발지, 도착지,
출발 시각, 경로 선호조건을 각각 채점한다. 이 평가는 문장 해석만 확인하며,
장소의 DB 존재 여부, 실제 보행 가능성, 추천 경로의 현장 안전을 보장하지 않는다.

## 2026-10-02 새 질문 100개

- route_intent_prospective_probe_20261002.json: 30개. 첫 실행 뒤 오류 분석과
  코드 수정에 사용했으므로 이제 개발·회귀 질문이다.
- route_intent_prospective_reserve_20261002.json: 30개. 수정 중에는 실행하지
  않았던 예약 평가셋이다. 첫 실행은 27/30이었고 실패 3건을 확인한 뒤
  더 이상 미공개 평가셋으로 취급하지 않는다.
- route_intent_prospective_validation_20261002.json: 추가 20개. 예약 평가의
  실패를 수정하기 전에 기대값을 작성했다. 첫 실행 17/20, 실패 분석 후
  보정한 회귀 실행 20/20.
- route_intent_prospective_final_20261002.json: 추가 20개. 이전 보정 전에
  기대값을 작성했다. 첫 실행 17/20, 실패 분석 후 보정한 회귀 실행 20/20.
- 네 파일은 기존 질문과 문자열이 겹치지 않도록 테스트한다. 중립/허용, 비교,
  정정, 시각, 복합조건, 장소 누락, 미지원 조건을 포함한다.
- 질문과 기대값은 Codex가 초안 작성·자체 검토했다. 별도의 참여자가 작성하고
  독립된 사람이 정답을 승인한 자료가 아니므로 '사람 검수 평가셋'이나
  실제 사용자 정확도로 부르지 않는다. 팀원 검수 전 상태로 관리한다.

실행: python -m evals.evaluate_intent --set prospective_probe_20261002 --quiet
예약 평가: python -m evals.evaluate_intent --set prospective_reserve_20261002 --quiet
새 질문 첫 평가: python -m evals.evaluate_intent --set prospective_validation_20261002 --quiet
추가 질문 첫 평가: python -m evals.evaluate_intent --set prospective_final_20261002 --quiet

평가 요약의 categories에서 유형별 정답 수와 출발지·도착지·시각·조건
오류, 요청하지 않은 조건 추가, 필요한 조건 누락, 방향 오류를 확인한다.
기존 --set all에는 이번 질문을 의도적으로 포함하지 않았다.
수정 과정에서 본 질문을 새로운 미공개 질문처럼 재사용하지 않기 위해서다.
