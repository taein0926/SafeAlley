import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { readFileSync } from "node:fs";
import { createExampleTyper } from "./exampleTyping.ts";
import { createPreviewScheduler } from "./liveIntentPreview.ts";
import { emptyConditionCards } from "./conditionCards.ts";

async function until(predicate: () => boolean) {
  for (let i = 0; i < 200; i++) { if (predicate()) return; await sleep(5); }
  assert.fail("Example typing event did not arrive");
}

test("manual interaction stops animation before the browser edits the textarea", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /onBeforeInput=\{\(\) => exampleTyper.current\?\.cancel\(\)\}/);
  assert.match(app, /onPointerDown=\{\(\) => exampleTyper.current\?\.cancel\(\)\}/);
  assert.match(app, /event.key === "Escape".*event.key === "Backspace".*event.key === "Delete"/);
  assert.match(app, /queryInputRef.current\?\.focus\(\)/);
});

test("examples append exactly one Unicode character and complete only on the final character", async () => {
  const texts: Array<{ text: string; complete: boolean }> = [];
  const states: boolean[] = [];
  const typer = createExampleTyper({
    onText: (text, complete) => texts.push({ text, complete }), onTypingChange: value => states.push(value),
    characterDelayMs: 1,
  });
  try {
    typer.start("밤 💡길");
    await until(() => texts.at(-1)?.complete === true);
    assert.deepEqual(texts.map(item => item.text), ["", "밤", "밤 ", "밤 💡", "밤 💡길"]);
    assert.equal(texts.filter(item => item.complete).length, 1);
    assert.equal(states.at(-1), false);
  } finally { typer.dispose(); }
});

test("spaces use the same default 25ms interval as every other character", (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const texts: string[] = [];
  const typer = createExampleTyper({ onText: text => texts.push(text), onTypingChange() {} });
  try {
    typer.start("밤 길");
    for (const expected of ["밤", "밤 ", "밤 길"]) {
      const count = texts.length;
      context.mock.timers.tick(24);
      assert.equal(texts.length, count);
      context.mock.timers.tick(1);
      assert.equal(texts.at(-1), expected);
    }
  } finally { typer.dispose(); }
});

test("cancel prevents late characters overwriting manual input; a replacement starts fresh", async () => {
  const texts: string[] = [];
  const typer = createExampleTyper({ onText: text => texts.push(text), onTypingChange() {}, characterDelayMs: 10 });
  try {
    typer.start("밤 CCTV 많은 길");
    await until(() => texts.includes("밤 "));
    typer.cancel();
    const count = texts.length;
    await sleep(60);
    assert.equal(texts.length, count);
    typer.start("낮");
    await until(() => texts.at(-1) === "낮");
    assert.deepEqual(texts.slice(count), ["", "낮"]);
  } finally { typer.dispose(); }
});

test("starting another example cancels the previous timer and disposal stops all input", async () => {
  const texts: string[] = [];
  const typer = createExampleTyper({ onText: text => texts.push(text), onTypingChange() {}, characterDelayMs: 10 });
  typer.start("밤 CCTV 많은 길");
  await until(() => texts.includes("밤 "));
  const count = texts.length;
  typer.start("낮 안전시설");
  await until(() => texts.includes("낮 "));
  typer.dispose();
  const stopped = texts.length;
  await sleep(60);
  assert.equal(texts.length, stopped);
  assert.ok(texts.slice(count).every(text => !text.startsWith("밤")));
  typer.start("재시작 금지");
  assert.equal(texts.length, stopped);
});

test("typing reaches the preview pipeline at word boundaries and idle after final completion", async () => {
  const calls: string[] = [];
  const scheduler = createPreviewScheduler({
    request: async query => { calls.push(query); return { query, model: "unit-fixture", conditions: emptyConditionCards("not_applied") }; },
    onPending() {}, onEmpty() {}, onResult() {}, onError(error) { throw error; },
    boundaryDelayMs: 1, idleDelayMs: 30, minimumIntervalMs: 0,
  });
  const typer = createExampleTyper({ onText: text => scheduler.update(text), onTypingChange() {}, characterDelayMs: 10 });
  try {
    typer.start("밤 CCTV 많은 길");
    await until(() => calls.length === 4);
    assert.deepEqual(calls, ["밤", "밤 CCTV", "밤 CCTV 많은", "밤 CCTV 많은 길"]);
  } finally { typer.dispose(); scheduler.dispose(); }
});
