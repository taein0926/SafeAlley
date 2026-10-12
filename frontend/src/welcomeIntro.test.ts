import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { hasDismissedWelcome, rememberWelcomeDismissed, WELCOME_DISMISSED_KEY } from "./welcomeIntro.ts";
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
  assert.match(intro, /가로등·CCTV·보행시설과 도로망을 분석해/);
  assert.match(intro, /CONDITION_ORDER\.map/);
  assert.doesNotMatch(intro, /계단 회피 · 건널목 최소 · 가로등·CCTV 고려 · 추천 근거 제공/);
  assert.doesNotMatch(intro, /reopen|welcome-open|welcome-start|길찾기 시작하기|fetch\(|\/api\/|setTimeout|자동 닫힘/);
  assert.equal(intro.match(/className="welcome-agency-row"/g)?.length, 1);
  assert.match(intro, /onClick=\{dismissFromBackdrop\}/);
  for (const asset of ["ltmetric.png", "kma.png", "molit.png", "incheon.png", "michuhol-color.png", "osm.png", "police.png", "nfa.jpg"]) {
    assert.ok(readFileSync(new URL(`../public/branding/${asset}`, import.meta.url)).length > 0);
  }
});
