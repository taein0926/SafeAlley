import assert from "node:assert/strict";
import test from "node:test";
import { conditionDecisions, mergeWorkUpdate, progressMessages, queryRouteWithProgress } from "./routeProgress.ts";
import type { RouteCandidate, RouteQueryResponse } from "./types.ts";

test("routing messages update in place and remain visible before the final result", () => {
  const pending = { id: "candidate-shortest", message: "최단 후보 계산 중", state: "working" as const };
  const completed = { id: "candidate-shortest", message: "최단 후보 약 810m", state: "completed" as const };
  const updates = mergeWorkUpdate(mergeWorkUpdate([], pending), completed);
  assert.equal(updates.length, 1);
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "주안역", destination_name: "병원", departure_time: null, profile: "pedestrian", preferences: [],
  };
  const messages = progressMessages("routing", interpretation, "주안역", "병원", null, updates);
  assert.equal(messages.at(-1)?.text, "최단 후보 약 810m");
  assert.equal(messages.at(-1)?.pending, false);
});

test("failed place resolution never claims confirmed coordinates or endless work", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "없는장소", destination_name: "병원", departure_time: null, profile: "pedestrian", preferences: [],
  };
  assert.deepEqual(progressMessages("failed", interpretation, null, null, null).map((message) => message.id), ["intent"]);
  assert.equal(progressMessages("failed", null, null, null, null)[0].pending, false);
});

test("route_progress reaches the UI callback while the HTTP response is still open", async () => {
  const originalFetch = globalThis.fetch;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  let resolveProgress: () => void = () => {};
  const arrived = new Promise<void>((resolve) => { resolveProgress = resolve; });
  globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) { streamController = controller; } }));
  try {
    let finished = false;
    const query = queryRouteWithProgress("질문", "test-user", (event) => {
      if (event.type === "route_progress") resolveProgress();
    }).then((result) => { finished = true; return result; });
    await Promise.resolve();
    streamController!.enqueue(new TextEncoder().encode(JSON.stringify({
      type: "route_progress", data: { id: "graph", message: "도로망 연결 확인", state: "completed" },
    }) + "\n"));
    await arrived;
    assert.equal(finished, false);
    streamController!.enqueue(new TextEncoder().encode('{"type":"result","data":{"model":"gemma4:26b"}}\n'));
    streamController!.close();
    assert.equal((await query).model, "gemma4:26b");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("stream parser handles split lines and returns the final result", async () => {
  const originalFetch = globalThis.fetch;
  const lines = [
    { type: "stage", stage: "interpreting" },
    { type: "interpreted", data: { preferences: [] } },
    { type: "result", data: { model: "gemma4:26b", result: { candidates: [] } } },
  ].map((event) => JSON.stringify(event)).join("\n") + "\n";
  const bytes = new TextEncoder().encode(lines);
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(bytes.slice(0, 17));
      controller.enqueue(bytes.slice(17, 59));
      controller.enqueue(bytes.slice(59));
      controller.close();
    },
  }));
  try {
    const received: string[] = [];
    const result = await queryRouteWithProgress("질문", "test-user", (event) => received.push(event.type));
    assert.deepEqual(received, ["stage", "interpreted", "result"]);
    assert.equal(result.model, "gemma4:26b");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("stream error never becomes a successful route", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('{"type":"error","detail":"장소를 찾지 못했습니다."}\n');
  try {
    await assert.rejects(queryRouteWithProgress("질문", "test-user", () => {}), /장소를 찾지 못했습니다/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Model preferences become explicit questions without invented probabilities", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "주안역", destination_name: "병원", departure_time: "22:00:00", profile: "pedestrian",
    preferences: [
      { factor: "stairs_distance_m", direction: "avoid", weight: 1 },
      { factor: "streetlight_score", direction: "maximize", weight: 1 },
    ],
  };
  const pending = conditionDecisions(interpretation, null);
  assert.deepEqual(pending.map((row) => row.answer), ["요청함", "요청함", "요청 없음", "요청 없음"]);
  assert.equal(pending[0].question, "계단을 피하고 싶은가?");
  assert.equal(pending[0].application, "경로 반영 여부 확인 중");
  const ready = conditionDecisions(interpretation, {
    recommendation_status: "ready", unsupported_preferences: [],
  } as RouteQueryResponse["result"]);
  assert.equal(ready[0].application, "경로 계산에 반영");
  assert.equal(ready[1].application, "경로 계산에 반영");
  assert.equal(ready[2].application, null);
});

test("daylight exclusion and withheld recommendations are not shown as applied", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: null, destination_name: null, departure_time: "13:00:00", profile: "pedestrian",
    preferences: [
      { factor: "streetlight_score", direction: "maximize", weight: 1 },
      { factor: "crosswalk_count", direction: "minimize", weight: 1 },
    ],
  };
  const ready = conditionDecisions(interpretation, {
    recommendation_status: "ready",
    unsupported_preferences: [{ factor: "streetlight_score", reason: "Excluded during daylight" }],
  } as RouteQueryResponse["result"]);
  assert.equal(ready[1].application, "주간 경로에서 제외");
  assert.equal(ready[3].application, "경로 계산에 반영");
  const withheld = conditionDecisions(interpretation, {
    recommendation_status: "field_review_required", unsupported_preferences: [],
  } as RouteQueryResponse["result"]);
  assert.equal(withheld[3].application, "추천 보류 — 적용 여부 미확정");
  const noRoute = conditionDecisions(interpretation, {
    recommendation_status: "no_supported_preferences",
    unsupported_preferences: [{ factor: "crosswalk_count", reason: "No generated route satisfies this hard avoidance condition" }],
  } as RouteQueryResponse["result"]);
  assert.equal(noRoute[3].application, "조건을 만족하는 경로 없음");
});

test("progress narration appears only after actual stage events and compares real route values", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "정부인천지방합동청사", destination_name: "두리하나어린이집", departure_time: "22:00:00", profile: "pedestrian",
    preferences: [
      { factor: "stairs_distance_m", direction: "avoid", weight: 1 },
      { factor: "streetlight_score", direction: "maximize", weight: 1 },
    ],
  };
  const candidate = (route_type: "shortest" | "custom", metrics: Record<string, number>) => ({ route_type, metrics }) as RouteCandidate;
  const result = {
    recommendation_status: "ready", selected_route_type: "custom", compared_route_type: "shortest",
    unsupported_preferences: [],
    candidates: [
      candidate("custom", { distance_m: 842, stairs_distance_m: 0, streetlight_score: 78.1 }),
      candidate("shortest", { distance_m: 746, stairs_distance_m: 18, streetlight_score: 50.3 }),
    ],
  } as RouteQueryResponse["result"];

  assert.deepEqual(progressMessages("interpreting", null, null, null, null).map((item) => item.id), ["intent"]);
  const resolving = progressMessages("resolving", interpretation, null, null, null);
  assert.deepEqual(resolving.map((item) => [item.id, item.pending]), [["intent", false], ["places", true]]);
  assert.match(resolving[0].text, /계단 회피/);
  assert.match(resolving[0].text, /가로등 위치 우선/);
  const routing = progressMessages("routing", interpretation, "정부인천지방합동청사", "두리하나어린이집", null);
  assert.deepEqual(routing.map((item) => [item.id, item.pending]), [["intent", false], ["places", false], ["routes", true]]);
  const done = progressMessages("done", interpretation, "정부인천지방합동청사", "두리하나어린이집", result);
  assert.equal(done.length, 3);
  assert.match(done[2].text, /842m.*746m/);
  assert.match(done[2].text, /맞춤 경로에 없고.*18m/);
  assert.match(done[2].text, /78\.1.*50\.3/);
  assert.equal(done[2].pending, false);
});

test("narration explains excluded daylight conditions without presenting them as applied", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "주안역", destination_name: "병원", departure_time: "13:00:00", profile: "pedestrian",
    preferences: [{ factor: "streetlight_score", direction: "maximize", weight: 1 }],
  };
  const result = {
    recommendation_status: "ready", selected_route_type: "shortest", compared_route_type: null,
    unsupported_preferences: [{ factor: "streetlight_score", reason: "Excluded during daylight" }],
    candidates: [{ route_type: "shortest", metrics: { distance_m: 900, streetlight_score: 50 } } as RouteCandidate],
  } as RouteQueryResponse["result"];
  const messages = progressMessages("done", interpretation, "주안역", "병원", result);
  assert.equal(messages[3].id, "limits");
  assert.match(messages[3].text, /낮 시간대라 계산에서 제외/);
  assert.doesNotMatch(messages[2].text, /가로등 위치 지표는/);
});

test("withheld result never invents a recommended route comparison", () => {
  const interpretation: RouteQueryResponse["interpretation"] = {
    origin_name: "주안역", destination_name: "병원", departure_time: null, profile: "pedestrian", preferences: [],
  };
  const result = {
    recommendation_status: "field_review_required", selected_route_type: null, compared_route_type: null,
    unsupported_preferences: [], candidates: [],
  } as RouteQueryResponse["result"];
  const messages = progressMessages("done", interpretation, "주안역", "병원", result);
  assert.match(messages[2].text, /자동 추천을 보류/);
  assert.doesNotMatch(messages[2].text, /맞춤 경로는 약/);
});
