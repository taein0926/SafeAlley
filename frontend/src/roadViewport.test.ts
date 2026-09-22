import assert from "node:assert/strict";
import test from "node:test";
import { roadBboxQuery, roadRequestBounds, viewportIsInside } from "./roadViewport.ts";

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
