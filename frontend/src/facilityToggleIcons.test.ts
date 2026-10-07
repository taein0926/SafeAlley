import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { facilityToggleFactor } from "./facilityToggleIcons.ts";
import { CCTV_MARKER_IMAGE } from "./facilityMarkers.ts";

test("facility controls map to the same condition icons as live analysis", () => {
  assert.deepEqual(["streetlights", "cctvs", "helpPoints", "stairsAndBridges"].map(kind => facilityToggleFactor(kind as Parameters<typeof facilityToggleFactor>[0])),
    ["streetlight", "cctv", "safety", "stairs"]);
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const cards = readFileSync(new URL("./components/RecommendationIcons.tsx", import.meta.url), "utf8");
  const icon = readFileSync(new URL("./components/ConditionIcon.tsx", import.meta.url), "utf8");
  assert.equal(app.match(/<ConditionIcon factor=\{facilityToggleFactor\(/g)?.length, 4);
  assert.match(cards, /<ConditionIcon factor=\{factor\} applied=\{applied\}/);
  assert.match(icon, /viewBox="0 0 40 40"/);
  assert.match(icon, /stroke="currentColor" strokeWidth="2.5"/);
  assert.doesNotMatch(app, /facilityToggleImage/);
});

test("only the stairs layer toggle suppresses the avoidance cross", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const icon = readFileSync(new URL("./components/ConditionIcon.tsx", import.meta.url), "utf8");
  assert.match(app, /factor=\{facilityToggleFactor\("stairsAndBridges"\)\} size=\{24\} showAvoidance=\{false\}/);
  assert.equal(app.match(/showAvoidance=\{false\}/g)?.length, 1);
  assert.match(icon, /showAvoidance = true/);
  assert.match(icon, /showAvoidance && \(factor === "stairs" \|\| factor === "crossing"\)/);
});

test("CCTV flips back from its previous UI direction while streetlight stays mirrored", () => {
  const icon = readFileSync(new URL("./components/ConditionIcon.tsx", import.meta.url), "utf8");
  assert.match(icon, /<g transform=\{factor === "streetlight" \? "translate\(40 0\) scale\(-1 1\)" : undefined\}>/);
  assert.equal(icon.match(/scale\(-1 1\)/g)?.length, 1);
});

test("facility hover labels stay concise in both map themes", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /aria-label="가로등 표시"[\s\S]*?title="가로등"/);
  assert.match(app, /aria-label="안전시설 표시"[\s\S]*?title="안전시설"/);
  assert.doesNotMatch(app, /title=\{nightMode \? "가로등|title="안전지원시설"/);
});

test("safety glyph is unfilled and CCTV reuses the map camera as an outline", () => {
  const icon = readFileSync(new URL("./components/ConditionIcon.tsx", import.meta.url), "utf8");
  const mapSvg = decodeURIComponent(CCTV_MARKER_IMAGE.split(",")[1]);
  assert.match(icon, /aria-hidden="true" fill="none" stroke="currentColor"/);
  assert.doesNotMatch(icon, /fill="currentColor"|fillOpacity=/);
  assert.doesNotMatch(icon, /<circle cx="22" cy="22" r="19"/);
  assert.match(icon, /rotate\(-25 22 22\)/);
  for (const geometry of ["M11 14h21v11H11zM7 17h4v6H7zM9 12h25v3H9z", "M23 26v6h10v-6"]) {
    assert.ok(mapSvg.includes(`d="${geometry}"`));
    assert.ok(icon.includes(`d="${geometry}"`));
  }
});
