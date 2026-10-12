import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createWelcomeCountdown, hasDismissedWelcome, rememberWelcomeDismissed, WELCOME_DISMISSED_KEY } from "./welcomeIntro.ts";

function clock() {
  let time = 0, nextId = 0, elapsed = 0;
  const ticks: number[] = [];
  const jobs = new Map<number, { at: number; callback: () => void }>();
  const timer = createWelcomeCountdown({
    now: () => time, onTick: value => ticks.push(value), onElapsed: () => elapsed++,
    schedule(callback, delay) { const id = ++nextId; jobs.set(id, { at: time + delay, callback }); return id; },
    cancel: id => { jobs.delete(id); },
  });
  function advance(ms: number) {
    const until = time + ms;
    for (;;) {
      const entry = [...jobs].sort((a, b) => a[1].at - b[1].at)[0];
      if (!entry || entry[1].at > until) break;
      time = entry[1].at; jobs.delete(entry[0]); entry[1].callback();
    }
    time = until;
  }
  return { timer, advance, ticks, jobs, get elapsed() { return elapsed; } };
}

test("welcome countdown dismisses once after eight active seconds", () => {
  const c = clock(); c.timer.resume(); c.timer.resume();
  assert.equal(c.jobs.size, 1);
  c.advance(7999); assert.equal(c.elapsed, 0);
  c.advance(1); assert.equal(c.elapsed, 1); assert.equal(c.ticks.at(-1), 0);
  c.timer.resume(); c.advance(10000); assert.equal(c.elapsed, 1);
});
test("reading pauses the countdown and resumes only the remaining duration", () => {
  const c = clock(); c.timer.resume(); c.advance(2500); c.timer.pause(); c.timer.pause();
  assert.equal(c.ticks.at(-1), 6); assert.equal(c.jobs.size, 0);
  c.advance(20000); assert.equal(c.elapsed, 0);
  c.timer.resume(); c.advance(5499); assert.equal(c.elapsed, 0);
  c.advance(1); assert.equal(c.elapsed, 1);
});
test("disposing prevents late dismissal and further timers", () => {
  const c = clock(); c.timer.resume(); c.advance(2000); c.timer.dispose();
  c.advance(20000); c.timer.resume(); assert.equal(c.elapsed, 0); assert.equal(c.jobs.size, 0);
});
test("dismissal is stored only for the browser session", () => {
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
  assert.equal(hasDismissedWelcome(storage), false); rememberWelcomeDismissed(storage);
  assert.equal(values.get(WELCOME_DISMISSED_KEY), "1"); assert.equal(hasDismissedWelcome(storage), true);
});
test("blocked browser storage does not prevent closing", () => {
  const blocked = { getItem(): string | null { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(hasDismissedWelcome(blocked), false); assert.doesNotThrow(() => rememberWelcomeDismissed(blocked));
  assert.equal(hasDismissedWelcome(null), false); assert.doesNotThrow(() => rememberWelcomeDismissed(null));
});
test("intro is wired to the app without any reopening control or model request", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const intro = readFileSync(new URL("./components/WelcomeIntro.tsx", import.meta.url), "utf8");
  assert.match(app, /<WelcomeIntro\s*\/>/); assert.match(intro, /element.showModal\(\)/);
  assert.match(intro, /맞춤 안전 보행 경로를 보여줍니다/);
  assert.doesNotMatch(intro, /reopen|welcome-open|fetch\(|\/api\//);
  for (const asset of ["ltmetric.png", "kma.png", "molit.png", "incheon.png", "michuhol-color.png", "osm.png", "police.png", "nfa.jpg"]) {
    assert.ok(readFileSync(new URL(`../public/branding/${asset}`, import.meta.url)).length > 0);
  }
});
