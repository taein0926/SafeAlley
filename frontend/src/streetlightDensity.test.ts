import assert from "node:assert/strict";
import test from "node:test";
import {
  densityCanvasPosition,
  densityDisplayAlpha,
  streetlightDensityBounds,
} from "./streetlightDensity.ts";

test("streetlight density bounds include padding around valid WGS84 points", () => {
  const bounds = streetlightDensityBounds([
    [126.67, 37.45],
    [126.69, 37.47],
    [Number.NaN, 37.46],
  ]);

  assert.ok(bounds);
  assert.ok(bounds.west < 126.67);
  assert.ok(bounds.east > 126.69);
  assert.ok(bounds.south < 37.45);
  assert.ok(bounds.north > 37.47);
});

test("north-west and south-east coordinates map to canvas corners", () => {
  const bounds = { west: 126, south: 37, east: 127, north: 38 };
  assert.deepEqual(densityCanvasPosition([126, 38], bounds, 800, 600), { x: 0, y: 0 });
  assert.deepEqual(densityCanvasPosition([127, 37], bounds, 800, 600), { x: 800, y: 600 });
  assert.deepEqual(densityCanvasPosition([126.5, 37.5], bounds, 800, 600), { x: 400, y: 300 });
});

test("empty or invalid input does not create density bounds", () => {
  assert.equal(streetlightDensityBounds([]), null);
  assert.equal(streetlightDensityBounds([[Number.NaN, Number.NaN]]), null);
});

test("density display removes sparse pixels and caps crowded hotspots", () => {
  assert.equal(densityDisplayAlpha(0), 0);
  assert.equal(densityDisplayAlpha(24), 0);
  assert.ok(densityDisplayAlpha(50) > 0);
  assert.equal(densityDisplayAlpha(255), 96);
});
