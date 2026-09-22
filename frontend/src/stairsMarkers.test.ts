import assert from "node:assert/strict";
import test from "node:test";
import { stairMarkerPosition } from "./stairsMarkers.ts";

test("stair marker follows half the line length rather than half its vertex count", () => {
  assert.deepEqual(stairMarkerPosition([[126, 37], [126.001, 37], [126.01, 37]]), [126.005, 37]);
  assert.deepEqual(stairMarkerPosition([[126, 37], [126, 37]]), [126, 37]);
});
test("invalid and missing stair geometry has no invented marker", () => {
  assert.equal(stairMarkerPosition([]), null);
  assert.equal(stairMarkerPosition([[126, 37]]), null);
  assert.equal(stairMarkerPosition([[126, 37], [NaN, 37]]), null);
});
