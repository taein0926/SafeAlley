import assert from "node:assert/strict";
import test from "node:test";
import {createPreviewCompletion} from "./previewCompletion.ts";

function setup() {
  let now = 0, id = 0, complete = false;
  const timers = new Map<number, {at: number; fn: () => void}>();
  const tracker = createPreviewCompletion({
    onChange: value => { complete = value; },
    schedule: (fn, delay) => { timers.set(++id, {at: now + delay, fn}); return id; },
    cancel: timer => { timers.delete(timer); },
  });
  return {tracker, completed: () => complete, advance(ms: number) {
    now += ms;
    for (const [key, timer] of timers) if (timer.at <= now) { timers.delete(key); timer.fn(); }
  }};
}

test("fast response stays analyzing until two seconds after input", () => {
  const s = setup(); s.tracker.edit("계단 피하고"); s.tracker.accept("계단 피하고");
  s.advance(1999); assert.equal(s.completed(), false);
  s.advance(1); assert.equal(s.completed(), true);
});
test("slow response never completes on quiet time alone", () => {
  const s = setup(); s.tracker.edit("CCTV 많은 길"); s.advance(3000);
  assert.equal(s.completed(), false); s.tracker.accept("CCTV 많은 길"); assert.equal(s.completed(), true);
});
test("one-second pauses and resumed typing restart the display timer", () => {
  const s = setup(); s.tracker.edit("계단"); s.tracker.accept("계단"); s.advance(1000);
  s.tracker.edit("계단 피하고"); s.tracker.accept("계단 피하고"); s.advance(1000);
  assert.equal(s.completed(), false); s.advance(1000); assert.equal(s.completed(), true);
  s.tracker.edit("계단 피하고 CCTV"); assert.equal(s.completed(), false);
});
test("old prefix response cannot complete the revised text", () => {
  const s = setup(); s.tracker.edit("계단 피하고 CCTV"); s.advance(2000);
  s.tracker.accept("계단 피하고"); assert.equal(s.completed(), false);
});
test("reset or dispose cancels pending completion", () => {
  const s = setup(); s.tracker.edit("밤 10시"); s.tracker.accept("밤 10시"); s.tracker.reset();
  s.advance(2000); assert.equal(s.completed(), false);
  s.tracker.edit("CCTV"); s.tracker.accept("CCTV"); s.tracker.dispose();
  s.advance(2000); assert.equal(s.completed(), false);
});
