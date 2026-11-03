# Optional Laya provider for live intent preview

## 현재 구성: PC Laya ONNX (2026-10-29 전환)

현재 로컬·VM은 PC CPU의 Laya ONNX FP32 실행기를 사용한다. 설치·이미지/모델 이관·SSH 연결은
[PC AI 운영 안내](../deployment/pc_ai/README.md)를 따른다. 최종 검색은 PC Gemma E2B,
음성은 PC Whisper small CPU이며 VM은 모델을 실행하지 않는다.

- 로컬 backend URL: `http://pc-laya:18761`.
- VM backend URL: `http://host.docker.internal:18763` → VM 전달기·역방향 SSH → PC loopback `18761`.
- 모델 ID: `laya-b3522f4d7939`. checkpoint SHA-256은 아래 계약과 동일하다.
- PC AI override는 provider=laya, Laya 활성, Jev 비활성을 설정한다. 일반 템플릿 기본값은 별도다.
- 상태 API의 세 true와 실제 POST 응답의 해시·8개 카드 판정을 확인한다.
  모델 미준비·상태 오류 뒤 화면은 5초 간격으로 재확인하고 준비 후 현재 입력을 분석한다.
- 연결 실패 시 유료 Jev 자동 대체는 없다. VM·PC 환경파일 변경은 실제 Compose 조합으로 재생성해야 한다.
- PC 모델·실행 이미지·비공개 설정·DB는 Git과 소스 압축본에 포함하지 않는다.

## 이전 GPU 전환·평가 기록

아래는 2026-10-21~22 GPU 서비스 전환 당시의 계약·검증 기록이다.
아래 GPU 주소·systemd·터널·모델 설치 명령을 현재 PC 구성에 적용하지 않는다.
API 계약과 backend 보정 흐름은 참고하되, 현재 실행 주소·기동·복구는 위 PC AI 안내를 기준으로 한다.

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

### Source/package alignment follow-up (2026-10-22)

Read-only checks on the deployed browser found the four unchanged examples
correct, but both orders of coordinated negation and individual negation still
incorrectly activated obstacle cards. This is not a passing deployment test.
The exact VM image revision was not retrieved. Remote main did not include
MR !13's `75cacd6` correction at the time of the check.

The repository's bundled `SafeAlley-deploy.tar.gz` also contained older source
(`release.json` base commit `953420b`), without either explicit-negative fix.
The distributable is refreshed from a pinned corrected commit. The package
test compares all Laya adapter/refinement modules and the preview HTTP router
against the checkout (normalizing Git/Windows line endings), and verifies the
archive checksum and per-file manifest hashes. This detects source/archive
drift without connecting to the VM or changing runtime settings.

`tests/test_laya_http_negation_regression.py` adds twelve HTTP-boundary cases:
individual/shared negation, both noun orders, short/full inputs, and all four
original browser examples read directly from the unchanged frontend source.
Wrong-positive model fixtures must be corrected in the response sent to the
browser. The test checks the selected Laya model ID, final states/directions,
and that no Jev call is made. These are offline fixture tests, not new GPU
inference or proof that the updated archive is running on the VM.

No further model training, phrase rules, frontend/example edits, provider
switch, database migration or production deployment is performed by this
follow-up. The operator must deploy the corrected archive through the existing
reviewed VM update process, then repeat the browser checks. Rebuilding only
the frontend does not update this Python backend correction.

After deployment approval: verify GPU hash/health and private connectivity,
apply only the provider settings, rebuild/recreate the backend with the actual
deployment's Compose files, then test cards plus an actual Gemma route. Review
timeouts/concurrency and process supervision. No database migration is needed
for this provider addition. Do not start the separate pilot DB in production.

Rollback: restore `INTENT_PREVIEW_PROVIDER=jev`, the operator's prior
`JEV_PREVIEW_ENABLED` and securely stored key, set `LAYA_PREVIEW_ENABLED=false`,
and recreate only the backend. Do not modify model files, DB volumes, map/UI or
the final Gemma route configuration during either change.
