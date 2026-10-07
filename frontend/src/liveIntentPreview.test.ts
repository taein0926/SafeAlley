import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { conditionCards, emptyConditionCards } from "./conditionCards.ts";
import { createPreviewScheduler, previewUnavailableMessage, requestIntentPreview, type PreviewResponse } from "./liveIntentPreview.ts";

const result = (query: string): PreviewResponse => ({ query, model: "jev-test", conditions: emptyConditionCards("not_applied") });

test("disabled or unavailable preview keeps route search available without a quota message", () => {
  assert.match(previewUnavailableMessage({ enabled: true, configured: true, available: false }), /연결되지/);
  assert.match(previewUnavailableMessage({ enabled: false, configured: true, available: false }), /꺼져/);
  assert.match(previewUnavailableMessage(null), /경로 검색은 계속/);
});
async function until(predicate: () => boolean) {
  for (let i = 0; i < 200; i++) { if (predicate()) return; await sleep(5); }
  assert.fail("Preview event did not arrive");
}

test("seven cards preserve actual API decisions without inferring new conditions", () => {
  const cards = conditionCards(["safety"], [{ factor: "streetlight", state: "applied" }, { factor: "time", state: "applied", period: "night" }]);
  assert.equal(cards.length, 7);
  assert.equal(cards.find((card) => card.factor === "cctv")?.state, "not_applied");
  assert.equal(cards.find((card) => card.factor === "time")?.period, "night");
});

test("word boundaries are coalesced and the whole latest prefix is sent once", async () => {
  const calls: string[] = [];
  const outputs: string[] = [];
  const scheduler = createPreviewScheduler({
    request: async (query) => { calls.push(query); return result(query); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult(data) { outputs.push(data.query); },
    boundaryDelayMs: 10, idleDelayMs: 20, minimumIntervalMs: 0,
  });
  try {
    scheduler.update("밤 "); scheduler.update("밤 10시에 "); scheduler.update("밤 10시에 계단을 피하고 ");
    await until(() => outputs.length === 1);
    assert.deepEqual(calls, ["밤 10시에 계단을 피하고"]);
    scheduler.update("밤 10시에 계단을 피하고  ");
    await sleep(30);
    assert.equal(calls.length, 1);
  } finally { scheduler.dispose(); }
});

test("late response cannot overwrite revised negation and only one request is in flight", async () => {
  const calls: string[] = [];
  const outputs: string[] = [];
  const resolvers: Array<(response: PreviewResponse) => void> = [];
  const scheduler = createPreviewScheduler({
    request: (query) => { calls.push(query); return new Promise((resolve) => resolvers.push(resolve)); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult(data) { outputs.push(data.query); },
    boundaryDelayMs: 1, minimumIntervalMs: 0,
  });
  try {
    scheduler.update("계단을 피해서 ");
    await until(() => calls.length === 1);
    scheduler.update("계단은 피하지 않아도 돼. CCTV가 많은 길 ");
    await sleep(20);
    assert.equal(calls.length, 1);
    resolvers[0](result(calls[0]));
    await until(() => calls.length === 2);
    assert.equal(outputs.length, 0);
    resolvers[1](result(calls[1]));
    await until(() => outputs.length === 1);
    assert.deepEqual(outputs, ["계단은 피하지 않아도 돼. CCTV가 많은 길"]);
  } finally { scheduler.dispose(); }
});

test("pausing for route search prevents queued previews and ignores pending results", async () => {
  let resolve: (value: PreviewResponse) => void = () => {};
  let calls = 0;
  let outputs = 0;
  const scheduler = createPreviewScheduler({
    request: () => { calls++; return new Promise((done) => { resolve = done; }); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult() { outputs++; },
    boundaryDelayMs: 1, minimumIntervalMs: 0,
  });
  scheduler.update("가로등 많은 길 ");
  await until(() => calls === 1);
  scheduler.update("CCTV도 많은 길 ");
  scheduler.pause();
  resolve(result("가로등 많은 길"));
  await sleep(25);
  assert.equal(calls, 1); assert.equal(outputs, 0);
  scheduler.dispose();
});

test("preview API contract sends only the query and rejects invalid card states", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_url, init) => {
    assert.deepEqual(JSON.parse(String(init?.body)), { query: "계단 피하기" });
    return new Response(JSON.stringify(result("계단 피하기")));
  };
  try {
    assert.equal((await requestIntentPreview("계단 피하기")).conditions.length, 7);
    globalThis.fetch = async () => new Response(JSON.stringify({ ...result("계단 피하기"), conditions: [{ factor: "stairs", state: "pending" }] }));
    await assert.rejects(requestIntentPreview("계단 피하기"));
  } finally { globalThis.fetch = original; }
});
