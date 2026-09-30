import assert from "node:assert/strict";
import test from "node:test";
import {
  densityCanvasPosition,
  densityDisplayAlpha,
  densityDisplayColor,
  densityKernelRadii,
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

test("density kernel represents the same 45m radius on both map axes", () => {
  const bounds = { west: 126.6, south: 37.4, east: 126.7, north: 37.5 };
  const radii = densityKernelRadii(bounds, 768);
  const metersPerLongitudeDegree = 111_320 * Math.cos(37.45 * Math.PI / 180);
  assert.ok(Math.abs(radii.x * (bounds.east - bounds.west) * metersPerLongitudeDegree / 768 - 45) < 0.01);
  assert.ok(Math.abs(radii.y * (bounds.north - bounds.south) * 111_320 / 768 - 45) < 0.01);
});

test("empty or invalid input does not create density bounds", () => {
  assert.equal(streetlightDensityBounds([]), null);
  assert.equal(streetlightDensityBounds([[Number.NaN, Number.NaN]]), null);
});

test("density display includes fewer lights while still capping crowded hotspots", () => {
  assert.equal(densityDisplayAlpha(0), 0);
  assert.equal(densityDisplayAlpha(20), 0);
  assert.equal(densityDisplayAlpha(35), 65);
  assert.equal(densityDisplayAlpha(50), 65);
  assert.equal(densityDisplayAlpha(90), 126);
  assert.equal(densityDisplayAlpha(255), 150);
});

test("relative density colors progress from purple through amber to lime", () => {
  assert.deepEqual(densityDisplayColor(0), [72, 40, 120]);
  assert.deepEqual(densityDisplayColor(100), [245, 162, 61]);
  assert.deepEqual(densityDisplayColor(150), [184, 242, 90]);
  assert.deepEqual(densityDisplayColor(999), [184, 242, 90]);
});
