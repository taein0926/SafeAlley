import assert from "node:assert/strict";
import test from "node:test";
import { roadBboxQuery } from "./roadViewport.ts";

const neighborhood = { west: 126.68, south: 37.46, east: 126.69, north: 37.47 };

test("shared building and facility bbox query uses WGS84 west,south,east,north order", () => {
  assert.equal(roadBboxQuery(neighborhood), "126.680000,37.460000,126.690000,37.470000");
});
