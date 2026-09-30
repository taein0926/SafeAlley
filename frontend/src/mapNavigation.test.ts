import assert from "node:assert/strict";
import test from "node:test";
import { JUAN_INITIAL_VIEW, zoomTargetHeight } from "./mapNavigation.ts";

test("home control shares the original Juan station view", () => {
  assert.deepEqual(JUAN_INITIAL_VIEW, { longitude: 126.6804, latitude: 37.4649, height: 1400 });
});
test("zoom steps are reversible within safe height bounds", () => {
  assert.equal(zoomTargetHeight(1400, "in"), 700);
  assert.equal(zoomTargetHeight(700, "out"), 1400);
  assert.equal(zoomTargetHeight(30, "in"), 30);
  assert.equal(zoomTargetHeight(2_000_000, "out"), 2_000_000);
  assert.equal(zoomTargetHeight(NaN, "in"), 700);
});
