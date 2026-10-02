# 자연어 경로 요청 해석 개선 (2026-10-02)

## 기준 환경

- 코드 기준: GitLab main `649887b`에서 만든 로컬 브랜치 `codex/intent-quality-20261002`
- 통합 실행: `safealley-colleague` Compose 프로젝트의 `3002` 화면, `8001` FastAPI, `safealley-colleague_postgis_data` 볼륨
- 이 DB는 담당자 전달 백업을 복원한 로컬 스냅샷이다. 담당자 컴퓨터의 DB와 실시간 동기화되지는 않는다.
- 별도 `3001/8000` 로컬 앱은 혼동 방지를 위해 중지했고, 그 DB 볼륨은 삭제하지 않았다.

## 발견한 문제와 수정 원리

Qwen3:4b가 자연어를 먼저 Structured Output으로 해석하는 구조는 유지했다. 모델, Tool Router, 장소 Resolver, 경로 알고리즘은 교체하지 않았다. 수정 범위는 FastAPI 백엔드의 출력 검산이다.

1. **정정한 출발 시각이 거절됨.** “오전 8시가 아니라 오전 9시 15분”에서 모델이 09:15를 출력해도 기존 검증은 첫 시각 08:00과 비교해 응답을 거절했다. 이제 시각 표현의 역할을 출발·도착·미지정으로 구분하고, 명확한 정정이 있을 때 확정된 출발 시각을 검증한다.
2. **도착 예정 시각을 출발 시각으로 오해할 수 있음.** “오후 2시에 도착”만 말한 경우 `departure_time`은 비워 둔다. 도착 시각과 출발 시각이 함께 있으면 출발 시각만 사용한다. 여러 시각의 관계가 모호하면 코드가 임의로 시간을 덮어쓰지 않는다.
3. **도착 기한만으로 최단거리 선호가 추가됨.** “오후 2시까지 도착”은 `distance_m/minimize` 요청과 다르다. 도착 기한이 있고 명시적인 짧은 길 요청이 없을 때만 모델이 추가한 거리 선호를 제거한다. “짧은 길로”가 함께 있으면 유지한다.

새 프롬프트 문구를 시험했을 때 기존 두 문장의 조건 추출이 흔들려 프롬프트 수정은 되돌렸다. 특정 문장마다 예외를 더하는 대신 역할 구분과 명시적 조건 검산을 적용했다.

## 검증 결과

| 검사 | 결과 | 해석 |
| --- | --- | --- |
| 시각 역할 진단 8문장 | 첫 수정 7/8, 최종 8/8 | 실패를 본 뒤 고쳤으므로 회귀셋으로 편입 |
| 기존·신규 전체 자연어 195문장 | 최종 195/195 | 대부분 이미 본 질문이므로 실사용 일반화 정확도 아님 |
| 백엔드 단위 테스트 | 227 통과 | DB를 변경하지 않는 별도 컨테이너에서 실행 |
| 담당자 DB 연결 API | 시각 정정 23:00, 후보 2개, 추천 `ready` | `POST /api/agent/query` 실제 Qwen·장소 검색·Tool 실행 |
| 첫 화면 대표 질문 | 22:00, 조건 2개, 후보 2개, 추천 `ready` | 담당자 DB 스냅샷 기준 종단 간 확인 |

평가에서 모델 응답 캐시는 끄고 각 문장을 새로 해석했다. 전체 195문장의 요청하지 않은 조건 추가, 조건 누락, 방향 오류는 최종 실행에서 모두 0건이었다. 이 수치는 경로의 실제 보행 가능성이나 안전성을 검증한 결과가 아니다. 다른 사람이 정답을 먼저 확정한 미사용 질문으로 후속 평가가 필요하다.

재현:

```powershell
docker compose -p safealley-colleague exec -T backend python -m pytest -q tests/unit
docker compose -p safealley-colleague exec -T backend python -m evals.evaluate_intent --set time_role_probe --quiet
docker compose -p safealley-colleague exec -T backend python -m evals.evaluate_intent --set all --quiet
```
