import assert from "node:assert/strict";
import test from "node:test";
import { INITIAL_MAP_VIEW, zoomTargetHeight } from "./mapNavigation.ts";

test("home control shares the closer government complex initial view", () => {
  assert.deepEqual(INITIAL_MAP_VIEW, { longitude: 126.66204388583374, latitude: 37.46883423059321, height: 1000 });
});
test("zoom steps are reversible within safe height bounds", () => {
  assert.equal(zoomTargetHeight(1400, "in"), 700);
  assert.equal(zoomTargetHeight(700, "out"), 1400);
  assert.equal(zoomTargetHeight(30, "in"), 30);
  assert.equal(zoomTargetHeight(2_000_000, "out"), 2_000_000);
  assert.equal(zoomTargetHeight(NaN, "in"), 500);
});
