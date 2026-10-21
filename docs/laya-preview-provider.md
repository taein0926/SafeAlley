# Optional Laya provider for live intent preview

## 현재 운영 적용 (2026-10-21)

아래 원래 MR 설명과 기본값은 유지하되, 현재 로컬·VM의 실제 선택은 GPU Laya입니다.
최종 Gemma 검색·Whisper·DB·HTTPS는 그대로입니다. 새 설치가 자동으로 Laya를 켠다는 뜻은 아닙니다.

- GPU `safealley-laya.service`: 기존 `server.py --mode gpu`를 관리하고 실패 시 재시작합니다. 모델 가중치를 복사하거나 재학습하지 않습니다.
- VM `safealley-laya-tunnel.service`: 별도 `safealley_laya` 키로 GPU의 `127.0.0.1:18761`에만 연결합니다. 기존 Gemma·Whisper 키·서비스와 분리합니다.
- VM backend의 실제 URL은 `http://host.docker.internal:18762`입니다. host gateway `172.17.0.1`에만 바인딩하고 방화벽으로 SafeAlley Docker 대역만 허용합니다.
- 고정 운영 `runtime/compose.json`은 이미 `private/service-env/backend.env`를 raw env_file로 읽습니다. 이 파일에 아래 provider 설정 5개를 넣고 기존 runtime으로 backend만 재생성합니다. 운영 runtime을 신규 Compose 예시로 대체하지 않습니다.
- 일반 로컬 Compose에서는 아래 선택 override를 반드시 유지합니다. VM은 사용자 노트북의 SSH 연결에 의존하지 않습니다.
- 상태 API와 실제 POST 응답의 모델 ID·조건 판정을 함께 확인합니다. 현재 updater의 status만으로 Laya 판정까지 검증된 것은 아닙니다.

운영 전환 시 DB·설정 백업과 이전 `backend.env`를 `private/updates/laya-provider-*`에 보관합니다.
provider 전환만 되돌릴 때는 해당 이전 env를 안전하게 복원하고 고정 runtime의 backend만 재생성합니다.
앱 이미지 rollback은 env_file 내용을 되돌리지 않으므로 `runtime/update.py rollback`만으로 Jev가 복구된다고 생각하면 안 됩니다.
키·인증서·DB 볼륨·모델 가중치를 삭제하지 않습니다. [운영 구성](../deployment/README.md)을 함께 확인합니다.

## Scope and default behavior

This change adds an **opt-in** replacement for input-time Jev requirement cards.
It does not replace the final Gemma route parser, routing tools, database, map,
frontend, STT or weather service. `INTENT_PREVIEW_PROVIDER=jev` remains the default;
`LAYA_PREVIEW_ENABLED=false` remains the default. The existing Jev API client and
its validation code are unchanged. Merging this MR is not an operational switch.

No model weights, credentials, raw spatial datasets, DB backups or exploratory
training/evaluation programs are included. The existing pilot is preserved.

## Selected model and GPU service

This is a fine-tuned Laya checkpoint, not an Ollama model:

```text
Model ID: laya-b3522f4d7939
GPU checkpoint directory:
/home/ltmetric/codex-laya-compound-refine-20261020/candidate_checkpoint
model.safetensors SHA256:
b3522f4d79391a93d9272bccdd3a8aadec601b11e9a2be3ea248eb58dd49a9da
```

The existing GPU-side service uses:

```text
/home/ltmetric/codex-laya-live-test-20261020/server.py --mode gpu
/home/ltmetric/codex-laya-live-test-20261020/questions.json
Python: /home/ltmetric/codex-gev-eval/.venv/bin/python
Laya source: /home/ltmetric/codex-laya-ko-train-20261015/source
Loopback endpoint: http://127.0.0.1:18761
```

These service files are already on the GPU server, not provisioned or restarted
by this MR. The operator must check the existing process before starting another
one and arrange supervised startup/restart for an operational rollout. No GPU
model pull or training is required. Keep the API private; do not expose 18761 to
the Internet. The application does not need a TypeSafe key to use Laya.

### GPU API contract

- `GET /health` returns `checkpoint_sha256` equal to the configured hash.
- `POST /analyze` receives `{"query":"CCTV 많은 길로 가줘", "version":123}`.
- The response echoes `query` and `version`, includes `checkpoint_sha256`, and
  contains `answers` for all eight factors. Each answer has `type: "choice"`,
  `choice` and a finite numeric `confidence` from 0 to 1.
- `distance/safety/streetlight/cctv`: `apply`, `skip`, `pending`.
- `stairs/crossing`: `avoid`, `minimize`, `skip`, `pending`.
- `bridge`: `apply`, `avoid`, `minimize`, `skip`, `pending`.
- `time`: `day`, `night`, `skip`, `pending`.

## Request flow and backend files

```text
Browser POST /api/agent/intent-preview
  -> FastAPI selects the configured provider
  -> Laya adapter calls the private GPU API through an SSH tunnel
  -> verify fixed model hash, echoed input/version, choices and confidence
  -> map_hybrid_cards + base clause guard + v2 -> v3 -> v4 -> v5 -> v6
  -> return the existing eight-card response schema to the unchanged frontend
```

Entry point: `app/services/laya_preview_service.py::analyze_preview()`.
The `laya_clause_candidate*.py` filenames retain the **frozen sequential policy**;
they are not six selectable models. Include all these modules, not v6 alone.
`laya_departure_clock.py` reads explicit departure clocks and uses the existing
route-time policy. Jev's pure Python helper functions are reused locally, not
the paid API. Incomplete requests, completed conditions, shared predicates,
negation/permission and explanatory questions are handled in the fixed guards.

The adapter references existing `jev_preview_service`, `incomplete_conditions`,
`local_llm_service`, `weather_service` and `schemas/intent_preview`. They are not
overwritten with older pilot copies. In particular main's removed slope
condition is not restored.

A Laya request has a 15-second HTTP timeout and no automatic Jev fallback.
Connection failure or wrong/stale model response returns HTTP 503. The status
route probes health with a 2-second timeout. It must be checked before rollout.

## Configuration and connectivity

Set these in the selected backend deployment **only when switching is approved**:

```dotenv
INTENT_PREVIEW_PROVIDER=laya
LAYA_PREVIEW_ENABLED=true
LAYA_PREVIEW_URL=http://host.docker.internal:18762
LAYA_CHECKPOINT_SHA256=b3522f4d79391a93d9272bccdd3a8aadec601b11e9a2be3ea248eb58dd49a9da
JEV_PREVIEW_ENABLED=false
```

The original Compose files are intentionally unchanged to preserve their reviewed
deployment hashes and Jev behavior. Adding variables to `.env` alone does **not**
pass them to the container. Explicitly add
`-f deployment/compose.laya-preview.override.yml` after the normal Compose files,
then inspect the resolved configuration before recreating the backend. Adjust
the path relative to the operator's working directory. For example, from the
repository root, **configuration check only**:

```bash
docker compose --env-file deployment/.env -f docker-compose.yml -f deployment/compose.vm.override.yml -f deployment/compose.laya-preview.override.yml config --quiet
```

This does not start anything. Keep the actual deployment's normal file set and
project name; do not start a second stack by copying a different invocation.
Existing update tooling may not include optional overrides in its command set.
The operator must retain this override for subsequent recreates or integrate it
through their reviewed deployment process. No Compose hash allowlist is relaxed.

Keep the existing Gemma, DB and other environment settings unchanged. Real keys
must remain outside Git. Existing Jev credentials need not be copied to a Laya
container, or deleted from the operator's secure rollback configuration.

### Windows Docker pilot: verified connection

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18762:127.0.0.1:18761 -p 19922 ltmetric@211.58.157.60
```

Docker reaches the Windows-host tunnel through `host.docker.internal:18762`.
The previous PC proxy on 18760 is not in the request path.

### Ubuntu VM: operator integration, not deployed by this MR

The tunnel must run on the VM/in its Docker network, not on a developer PC.
Do not copy the Windows host URL blindly: a Linux host-gateway address does not
automatically reach a socket bound only to host loopback.

One option is an operator-managed SSH tunnel sidecar in the backend's private
Docker network, with no published host port. Then set `LAYA_PREVIEW_URL` to its
internal service URL (for example `http://laya-tunnel:18762`). That service name
is illustrative, **not an existing service created by this MR**. Use managed
SSH credentials and verified host keys; do not disable host-key checking.
Alternatively use an approved private host binding with narrowly scoped firewall
rules. Neither model nor DB ports need public forwarding.

## Frozen pilot evidence (2026-10-21)

Same synthetic Korean 64 sentences and gold, no rule changes or training during
the final comparison. Jev requested `jev-latest`, returned `jev-1.13.0`, 64/64
calls completed. All eight choice/direction/time/pending states must match.

| Metric | Laya + frozen v6 | Jev + existing guard |
| --- | ---: | ---: |
| Exact condition set | 62/64 (96.9%) | 58/64 (90.6%) |
| Sentences with missing requested conditions | 2 | 3 |
| Sentences with unwanted active conditions | 0 | 2 |
| Median response | 0.21 s | 0.21 s |

This compares **provider-specific guarded systems**, not unguarded base models.
Jev unguarded scored 55/64 (85.9%); unguarded Laya was not measured on this set.
Timing paths differ: Laya included local Docker/SSH/GPU/guard, Jev was a PC API
call plus local guard; route search, typing delay and rendering are excluded.
The fresh data is AI-authored, not an independent real-user or load study.

Prior pilot checks: saved-response replay 328/328, related backend tests 177,
input-scheduler tests 20, actual browser typing/deletion/replacement/clear plus
Gemma route lookup. One route smoke case was 1.13 km / estimated 16 minutes;
custom and shortest geometries were equal and the explanation said so. This is
not evidence that all requested constraints produce a distinct feasible route.
Those historical counts describe the pilot; new-main validation is reported in
the MR rather than passed off as an already-deployed check.

The GPU checkpoint's final gold-only continuation used 320 sentences x eight
answers, AdamW, encoder LR 1e-6/head LR 3e-6, one epoch/80 updates. No new training
is performed here. Laya removes per-request external API charges; compute,
electricity, monitoring and maintenance still have costs.

Local evidence directory (not committed):
`safealley-laya-pilot-20261020/pilot-data/v6-final-frozen-20261021/`, especially
`jev-laya-final64-comparison.json`, `jev-final64-results.json`, `final-summary.json`.
Documentation: https://app.notion.com/p/3fe86c3b70c7818da88ce496bb86ec10

## Validation, rollout and rollback

### Explicit negative evidence fix (2026-10-21, follow-up to merged MR !12)

The existing source-evidence parser already recognized `계단 피하지 않고` as
negative. The Laya mapper previously retained a native `avoid` prediction
because its explicit-choice recovery imported positive evidence only. The
mapper now sets that factor to `skip` / `not_applied`, clears its direction
and avoids presenting the native confidence as a corrected confidence.
It does not add new phrase patterns, change the model, or modify Jev guards.
Last-mention scoping and existing inverse-lighting refinements are retained.

Reported input: `계단 피하지 않고 건널목 피해서 갈래` now activates only
crossing avoidance. In the full reported night/light/CCTV example, stairs
stays off while streetlight, CCTV, crossing and time stay on.

### Coordinated obstacle negation follow-up (2026-10-21, MR !13)

`건널목과 계단은 피하지 말고 갈래` exposed a separate scope gap: the
shared parser stops the first noun's scope at the next noun. The earlier
single-factor fix therefore disabled only the last noun's card.

The Laya-only final guard now recognizes an immediately coordinated obstacle
list and checks the shared rejection separately for each named factor. It
reuses the existing cancellation/direct-rejection predicates and preserves the
remaining original query for last-mention checks. A later explicit positive
request still wins. Positive avoidance, `빼고`, and independent clauses remain
unchanged. The shared Jev parser, trained checkpoint, frontend and examples
are not modified.

Validation including both single-factor and coordinated-negation fixes:

| Check | Result |
| --- | ---: |
| Related backend regression tests, including 69 single/grouped-negation cases | 737 passed |
| Saved native Laya responses through the complete updated analysis pipeline | 328/328 |
| Live GPU Laya through isolated MR FastAPI, normal/negative/example requests | 28/28 |
| Actual browser example selections, final cards checked | 4/4 |
| Deployment package/update unit tests in isolated Linux container | 70 passed |

The 53 additional grouped-negation regression cases cover both orders of each
obstacle pair, all six three-factor permutations, noun-list connectors,
aliases, compact input, the reported full query, later positive corrections,
and unaffected positive/independent clauses. Live GPU checks cover the
reported full query and its reversed order, all obstacle-pair/triple orders,
and the four unchanged original browser examples. Browser verification uses
the isolated local test screen, not a production deployment.

The four example texts were read unchanged from `frontend/src/App.tsx` and
also selected in the browser at the isolated local verification screen:

| Browser example | Active conditions (all other cards off) |
| --- | --- |
| 가로등 · CCTV · 건널목 | Streetlight, CCTV, crossing avoid, night |
| 가로등 · CCTV · 계단 | Streetlight, CCTV, stairs avoid, night |
| 종합 조건 | All eight; stairs/crossing avoid, bridge prefer, night |
| 가로등 · 계단 | Streetlight, stairs avoid, night |

These are request-card correctness checks, not a guarantee that every desired
road constraint has a feasible distinct route. No additional training, paid
Jev calls, production configuration/DB changes, frontend or example edits
were made. GPU checkpoint and the default disabled/opt-in policy are unchanged.

The added tests use mocked Laya responses and never make paid API calls or touch
the operational DB. Run existing Jev tests as well as new `tests/test_laya*.py`
tests before switching. Confirm default provider is Jev, Laya is disabled, and
the same frontend contract is returned. Replay frozen evidence on latest main
as a separate offline check, since shared helper changes can affect results.

After deployment approval: verify GPU hash/health and private connectivity,
apply only the provider settings, rebuild/recreate the backend with the actual
deployment's Compose files, then test cards plus an actual Gemma route. Review
timeouts/concurrency and process supervision. No database migration is needed
for this provider addition. Do not start the separate pilot DB in production.

Rollback: restore `INTENT_PREVIEW_PROVIDER=jev`, the operator's prior
`JEV_PREVIEW_ENABLED` and securely stored key, set `LAYA_PREVIEW_ENABLED=false`,
and recreate only the backend. Do not modify model files, DB volumes, map/UI or
the final Gemma route configuration during either change.
