# 자연어 경로 요청 평가

`evaluate_intent.py`는 현재 설정된 Ollama에 문장을 보내 출발지·도착지·시각·
선호조건을 채점한다. 해석 캐시는 끄고 문장마다 새 응답을 받는다.
장소 DB, 경로 생성, 시설 밀집도, 현장 안전을 평가하는 도구는 아니다.

## 실행

Ollama 연결과 모델 준비는 [AI 실행 설정](../../docs/ai-setup.md)을 따른다.
아래 PowerShell 예시는 소스를 clone한 로컬 저장소 루트에서 실행한다.
실제 모델을 호출하므로 단위 테스트보다 오래 걸린다.

```powershell
docker compose exec backend python -m evals.evaluate_intent --set dev --quiet
docker compose exec backend python -m evals.evaluate_intent --set regression --quiet
docker compose exec backend python -m evals.evaluate_intent --set holdout --quiet
```

현재 VM은 소스를 상시 보관하지 않지만 평가 코드는 backend 이미지 안에 있다.
운영 GPU 부하를 허용받은 뒤에만 다음 고정 설정 명령을 사용한다. 배포 status의 모델 목록
확인은 이 live 평가를 실행했다는 의미가 아니다.

```bash
docker compose -p safealley-deploy -f ~/safealley-deploy/runtime/compose.json exec -T backend python -m evals.evaluate_intent --set dev --quiet
```

`--set all`은 위 세 묶음을 합친다. 다음 추가 세트는 별도로 실행한다.

```powershell
docker compose exec backend python -m evals.evaluate_intent --set prospective_probe_20261002 --quiet
docker compose exec backend python -m evals.evaluate_intent --set prospective_reserve_20261002 --quiet
docker compose exec backend python -m evals.evaluate_intent --set prospective_validation_20261002 --quiet
docker compose exec backend python -m evals.evaluate_intent --set prospective_final_20261002 --quiet
docker compose exec backend python -m evals.evaluate_intent --set acceptance_20261002 --quiet
```

세트 이름과 파일 매핑은 [evaluate_intent.py](evaluate_intent.py)의 `CASE_SETS`를
기준으로 한다. 특정 실패만 확인하려면 `--ids ID1,ID2`를 사용한다.

## 결과 해석

요약에는 필드별 오류, 요청하지 않은 조건 추가, 필요한 조건 누락, 선호 방향
오류, 강한 회피조건 오류, 지연시간 중앙값·95백분위, 실패 ID가 포함된다.
명령은 모든 사례가 기대값과 맞을 때만 종료 코드 0을 반환한다.

기존 질문은 개발 중 확인·보정에 사용한 회귀 자료다. 파일이나 세트 이름에
`holdout`, `prospective`가 있어도 새로운 미공개 질문의 정확도로 해석하지
않는다. 질문·기대값 초안은 독립된 사용자 검수 자료가 아니다.
실제 사용자 정확도를 평가하려면 새 질문과 별도 정답 검수가 필요하다.

과거 모델의 점수·속도와 당시 테스트 개수는 현재 서비스 성능으로 제공하지 않는다.
새 측정에서는 코드 revision, 모델, 실행 환경, 세트, 캐시 여부를 함께 기록한다.
현재 문장 해석 흐름은 [자연어 처리](../../docs/natural-language.md),
전체 회귀 테스트는 [테스트 안내](../../docs/testing.md)를 참고한다.
