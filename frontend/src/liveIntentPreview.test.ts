import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { CONDITION_LABELS, conditionCards, emptyConditionCards } from "./conditionCards.ts";
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

test("eight cards preserve actual API decisions without inferring new conditions", () => {
  const cards = conditionCards(["safety"], [{ factor: "streetlight", state: "applied" }, { factor: "time", state: "applied", period: "night" }]);
  assert.equal(cards.length, 8);
  assert.equal(cards.find((card) => card.factor === "cctv")?.state, "not_applied");
  assert.equal(cards.find((card) => card.factor === "time")?.period, "night");
});

test("condition cards always use the requested four-plus-four order with bridge after crossing", () => {
  const order = ["distance", "streetlight", "cctv", "safety", "stairs", "crossing", "bridge", "time"];
  assert.deepEqual(emptyConditionCards().map(card => card.factor), order);
  assert.deepEqual(conditionCards([], emptyConditionCards().reverse()).map(card => card.factor), order);
  assert.equal(CONDITION_LABELS.crossing, "건널목 회피");
  assert.equal(CONDITION_LABELS.bridge, "육교");
  const css = readFileSync(new URL("./routeCards.css", import.meta.url), "utf8");
  assert.match(css, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
});

test("bridge condition preserves the preview answer but never invents a completed routing preference", () => {
  const cards = conditionCards([], [{ factor: "bridge", state: "applied", direction: "avoid" }]);
  assert.equal(cards[6].factor, "bridge");
  assert.equal(cards[6].direction, "avoid");
  assert.equal(conditionCards([])[6].state, "not_applied");
  const icon = readFileSync(new URL("./components/ConditionIcon.tsx", import.meta.url), "utf8");
  const bridge = readFileSync(new URL("./bridgeMarkers.ts", import.meta.url), "utf8");
  const outline = 'M5 33h5v-6h5v-6h14v6h5v6h5';
  assert.ok(icon.includes(outline) && bridge.includes(outline));
  const badges = readFileSync(new URL("./components/RecommendationIcons.tsx", import.meta.url), "utf8");
  assert.match(badges, /factor === "bridge" \? "육교 선호는 현재 경로 비용에 독립적으로 반영되지 않습니다"/);
});

test("inactive condition cards use a clearer border without changing selected or analyzing cards", () => {
  const css = readFileSync(new URL("./routeCards.css", import.meta.url), "utf8");
  assert.match(css, /--result-inactive-badge-line: #64758a;/);
  assert.match(css, /--result-inactive-badge-line: #a7b2c0;/);
  assert.match(css, /\.recommendation-badge\[data-applied="false"\] \{[^}]*border-color: var\(--result-inactive-badge-line\);[^}]*border-style: dashed;/);
  assert.match(css, /\.recommendation-badge \{[^}]*border: 1px solid var\(--result-badge-line\);/);
  assert.match(css, /\.recommendation-badge\[data-state="analyzing"\] \{[^}]*border-color: #bd934c;/);
});

test("cards omit visible applied labels and footer hints but keep accessible state and errors", () => {
  const badges = readFileSync(new URL("./components/RecommendationIcons.tsx", import.meta.url), "utf8");
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(badges, /<small|recommendation-badge-status/);
  assert.match(badges, /aria-label=\{`\$\{CONDITION_LABELS\[factor\]\}: \$\{status\}`\}/);
  assert.doesNotMatch(app, /live-preview-hint|live-preview-notice|경로는 검색 후/);
  assert.match(app, /live-preview-state.*role="status".*title=\{livePreview.notice/);
});

test("example typing and manual input share preview while route search and mode switches cancel typing", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /setQuery\(text\);\s+livePreview.pause\(\);\s+beginSearch\("ai"\)/);
  assert.match(app, /onClick=\{\(\) => typeExample\(example\)\}/);
  assert.match(app, /livePreview.clear\(\);\s+setMode\(mode === "ai" \? "direct" : "ai"\)/);
  assert.match(app, /setQuery\(text\); livePreview.update\(text\)/);
  assert.match(app, /onChange=\{\(event\) => editQuery\(event.target.value/);
  assert.doesNotMatch(app, /onBlur=.*livePreview.update/);
  assert.match(app, /async function runAiSearch[\s\S]*?exampleTyper.current\?\.cancel\(\)/);
});

test("editing or selecting an example replaces results with preview without clearing map routes", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const example = app.slice(app.indexOf("function typeExample"), app.indexOf("function editQuery"));
  const edit = app.slice(app.indexOf("function editQuery"), app.indexOf("const processScrollRef"));
  for (const handler of [example, edit]) {
    assert.match(handler, /setQueryEditing\(true\)/);
    assert.match(handler, /setActiveSearchMode\(null\)/);
    assert.doesNotMatch(handler, /setSearchResult\(null\)|setSelectedRouteType\(null\)/);
  }
  assert.match(app, /const showSearchResults = !queryEditing && displayedCandidates.length > 0/);
  assert.match(app, /const showLivePreview = mode === "ai" && livePreview.active && !showSearchResults && requestState !== "loading"/);
  assert.match(app, /\{showLivePreview \? \(/);
  assert.match(app, /!queryEditing && activeSearchMode === "ai"/);
  for (const start of ["function beginSearch", "function finishSearch"]) {
    const handler = app.slice(app.indexOf(start), app.indexOf("\n  }", app.indexOf(start)));
    assert.match(handler, /setQueryEditing\(false\)/);
  }
});

test("completed route cards use only saved routing conditions, never live analysis or its status", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const results = app.slice(app.indexOf('{searchResult && searchResult.result.recommendation_status'), app.indexOf('</aside>', app.indexOf('{searchResult && searchResult.result.recommendation_status')));
  assert.doesNotMatch(results, /livePreview|live-preview-state|분석 중|previewRouteType/);
  assert.match(results, /conditions=\{searchResult\?\.result.recommendation_conditions\}/);
  const hook = readFileSync(new URL("./useLiveIntentPreview.ts", import.meta.url), "utf8");
  const update = hook.slice(hook.indexOf("const update ="), hook.indexOf("const pause ="));
  assert.ok(update.indexOf("setActive(true)") < update.indexOf("scheduler.current?.update(text)"));
});

test("word boundaries are coalesced and the whole latest prefix is sent once", async () => {
  const calls: string[] = [];
  const outputs: string[] = [];
  const scheduler = createPreviewScheduler({
    request: async (query) => { calls.push(query); return result(query); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult(data) { outputs.push(data.query); },
    boundaryDelayMs: 10, minimumIntervalMs: 0,
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

test("letters wait for idle; a space flushes even when trim is unchanged and the final word needs no blur", async () => {
  const calls: string[] = [];
  const scheduler = createPreviewScheduler({
    request: async query => { calls.push(query); return result(query); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult() {},
    boundaryDelayMs: 1, idleDelayMs: 60, minimumIntervalMs: 0,
  });
  try {
    scheduler.update("계"); scheduler.update("계단");
    await sleep(20);
    assert.deepEqual(calls, []);
    scheduler.update("계단 ");
    scheduler.update("계단 없"); // The next letter must not postpone the word snapshot.
    await until(() => calls.length === 1);
    assert.deepEqual(calls, ["계단"]);
    scheduler.update("계단 없는");
    await sleep(20);
    assert.equal(calls.length, 1);
    scheduler.update("계단 없는 ");
    await until(() => calls.length === 2);
    scheduler.update("계단 없는 길");
    await sleep(20);
    assert.equal(calls.length, 2);
    await until(() => calls.length === 3);
    assert.deepEqual(calls, ["계단", "계단 없는", "계단 없는 길"]);
    scheduler.update("계단 없는 길");
    await sleep(20);
    assert.equal(calls.length, 3);
  } finally { scheduler.dispose(); }
});

test("a completed prefix remains usable while more words are appended", async () => {
  const calls: string[] = [];
  const outputs: string[] = [];
  const resolvers: Array<(response: PreviewResponse) => void> = [];
  const scheduler = createPreviewScheduler({
    request: query => { calls.push(query); return new Promise(resolve => resolvers.push(resolve)); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult(data) { outputs.push(data.query); },
    boundaryDelayMs: 1, minimumIntervalMs: 0,
  });
  try {
    scheduler.update("가로등 많은 ");
    await until(() => calls.length === 1);
    scheduler.update("가로등 많은 길 CCTV도 ");
    resolvers[0](result(calls[0]));
    await until(() => calls.length === 2);
    assert.deepEqual(outputs, ["가로등 많은"]);
    resolvers[1](result(calls[1]));
    await until(() => outputs.length === 2);
    assert.deepEqual(outputs, ["가로등 많은", "가로등 많은 길 CCTV도"]);
  } finally { scheduler.dispose(); }
});

test("rapid boundaries coalesce under the minimum request interval", async () => {
  const calls: string[] = [];
  const times: number[] = [];
  const scheduler = createPreviewScheduler({
    request: async query => { calls.push(query); times.push(Date.now()); return result(query); },
    onPending() {}, onEmpty() {}, onError(error) { throw error; }, onResult() {},
    boundaryDelayMs: 1, minimumIntervalMs: 40,
  });
  try {
    scheduler.update("밤 ");
    await until(() => calls.length === 1);
    scheduler.update("밤 CCTV ");scheduler.update("밤 CCTV 많은 ");scheduler.update("밤 CCTV 많은 길 ");
    await until(() => calls.length === 2);
    assert.deepEqual(calls, ["밤", "밤 CCTV 많은 길"]);
    assert.ok(times[1] - times[0] >= 35);
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
    assert.equal((await requestIntentPreview("계단 피하기")).conditions.length, 8);
    globalThis.fetch = async () => new Response(JSON.stringify({ ...result("계단 피하기"), conditions: [{ factor: "stairs", state: "pending" }] }));
    await assert.rejects(requestIntentPreview("계단 피하기"));
  } finally { globalThis.fetch = original; }
});
