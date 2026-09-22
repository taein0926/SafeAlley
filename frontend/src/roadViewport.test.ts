import assert from "node:assert/strict";
import test from "node:test";
import { geometryBounds, roadBboxQuery, roadRequestBounds, viewportIsInside } from "./roadViewport.ts";

const neighborhood = { west: 126.68, south: 37.46, east: 126.69, north: 37.47 };

test("road requests skip city overview and invalid rectangles", () => {
  for (const view of [
    { ...neighborhood, east: 126.72 },
    { ...neighborhood, north: 37.49 },
    { ...neighborhood, east: 126.68 },
    { ...neighborhood, south: 38 },
    { ...neighborhood, west: NaN },
    { ...neighborhood, north: Infinity },
  ]) assert.equal(roadRequestBounds(view), null);
});

test("padded viewport supports small pans without another request", () => {
  const bounds = roadRequestBounds(neighborhood);
  assert.ok(bounds);
  assert.equal(roadBboxQuery(bounds), "126.676500,37.456500,126.693500,37.473500");
  assert.equal(viewportIsInside(neighborhood, bounds), true);
  assert.equal(viewportIsInside({ ...neighborhood, east: 126.692 }, bounds), true);
  assert.equal(viewportIsInside({ ...neighborhood, east: 126.7 }, bounds), false);
  assert.equal(viewportIsInside(bounds, bounds), true);
});

test("initial framing uses Polygon and MultiPolygon coordinates without road download", () => {
  assert.deepEqual(geometryBounds([
    [[[126.68, 37.46], [126.69, 37.47]]],
    [[[[126.67, 37.45, 10], [126.7, 37.48]]]],
    null, [[NaN, 37]],
  ]), { west: 126.67, south: 37.45, east: 126.7, north: 37.48 });
  assert.equal(geometryBounds([]), null);
});
