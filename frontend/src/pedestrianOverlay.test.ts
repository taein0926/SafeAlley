import assert from "node:assert/strict";
import test from "node:test";
import { isPedestrianOverlayFeature, PEDESTRIAN_OVERLAY_WIDTH, pedestrianRequestBounds } from "./pedestrianOverlay.ts";
import { viewportIsInside } from "./roadViewport.ts";

const geometry = { type: "LineString", coordinates: [[126.66, 37.46], [126.661, 37.461]] };

test("district-wide views still request pedestrian lines after zooming out", () => {
  const view = { west: 126.63, south: 37.43, east: 126.72, north: 37.49 };
  const bounds = pedestrianRequestBounds(view);
  assert.ok(bounds);
  assert.equal(viewportIsInside(view, bounds), true);
});

test("panning outside the loaded buffer requests the newly visible area", () => {
  const initial = { west: 126.65, south: 37.46, east: 126.67, north: 37.48 };
  const loaded = pedestrianRequestBounds(initial)!;
  const moved = { ...initial, west: 126.68, east: 126.70 };
  assert.equal(viewportIsInside(moved, loaded), false);
  assert.equal(viewportIsInside(moved, pedestrianRequestBounds(moved)!), true);
});

test("invalid and country-scale bounds do not request excessive geometry", () => {
  for (const view of [
    { west: 126, south: 37, east: 128, north: 38 },
    { west: NaN, south: 37, east: 127, north: 37.01 },
    { west: 127, south: 37, east: 126, north: 37.01 },
  ]) assert.equal(pedestrianRequestBounds(view), null);
});

test("pedestrian overlay shows separate walking geometry including crossings and stairs", () => {
  for (const highway of ["footway", "path", "pedestrian", "steps"]) {
    assert.equal(isPedestrianOverlayFeature({ properties: { highway, pedestrian_allowed: true }, geometry }), true);
  }
  assert.equal(isPedestrianOverlayFeature({ properties: { highway: "footway", footway: "crossing", pedestrian_allowed: true }, geometry }), true);
  assert.ok(PEDESTRIAN_OVERLAY_WIDTH <= 2);
});

test("all roads admitted by the pedestrian network are visible, including shared roads", () => {
  for (const highway of ["primary", "secondary", "tertiary", "residential", "service", "living_street", "cycleway", "track", "unclassified"]) {
    assert.equal(isPedestrianOverlayFeature({ properties: { highway, pedestrian_allowed: true }, geometry }), true);
  }
});

test("display-only layer includes vehicle-only and restricted roads regardless of walking access", () => {
  for (const highway of ["motorway", "trunk", "cycleway", "construction", "footway"]) {
    for (const pedestrian_allowed of [false, undefined, "true"]) {
      assert.equal(isPedestrianOverlayFeature({ properties: { highway, pedestrian_allowed }, geometry }), true);
    }
  }
});

test("invalid or incomplete pedestrian geometry is excluded", () => {
  for (const invalid of [
    { type: "Point", coordinates: geometry.coordinates },
    { type: "LineString", coordinates: [[126.66, 37.46]] },
    { type: "LineString", coordinates: [[126.66, NaN], [126.66, 37.46]] },
  ]) assert.equal(isPedestrianOverlayFeature({ properties: { highway: "footway", pedestrian_allowed: true }, geometry: invalid }), false);
});
