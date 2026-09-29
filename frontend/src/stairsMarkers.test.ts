import assert from "node:assert/strict";
import test from "node:test";
import { stairMarkerPosition, STAIRS_MARKER_IMAGE } from "./stairsMarkers.ts";

test("stair icon has an opaque light badge, solid steps and an ascent arrow", () => {
  const svg = decodeURIComponent(STAIRS_MARKER_IMAGE.split(",")[1]);
  assert.match(svg, /fill="#ffffff"/);
  assert.match(svg, /M8 35v-7h7v-7h7v-7h7V8h7v27Z/);
  assert.match(svg, /M8 20 20 8M12 8h8v8/);
  assert.doesNotMatch(svg, /<text|<image|<script/);
});

test("stair marker follows half the line length rather than half its vertex count", () => {
  assert.deepEqual(stairMarkerPosition([[126, 37], [126.001, 37], [126.01, 37]]), [126.005, 37]);
  assert.deepEqual(stairMarkerPosition([[126, 37], [126, 37]]), [126, 37]);
});
test("invalid and missing stair geometry has no invented marker", () => {
  assert.equal(stairMarkerPosition([]), null);
  assert.equal(stairMarkerPosition([[126, 37]]), null);
  assert.equal(stairMarkerPosition([[126, 37], [NaN, 37]]), null);
});
