import assert from "node:assert/strict";
import test from "node:test";
import { routeLineStyle, routeGeometrySignature, routePickPriority } from "./routePresentation.ts";
import type { RouteCandidate } from "./types.ts";

test("routes are 1.5 times wider and casing switches with the theme", () => {
  assert.equal(routeLineStyle("custom", "custom").width, 9);
  assert.equal(routeLineStyle("custom", "custom").casingWidth, 15);
  assert.equal(routeLineStyle("shortest", "custom").width, 6);
  assert.equal(routeLineStyle("shortest", "custom").casingWidth, 10.5);
  assert.equal(routeLineStyle("custom", "custom", false).casingColor, "#16365c");
  assert.equal(routeLineStyle("custom", "custom", true).casingColor, "#ffffff");
});

test("active route is blue above the gray alternative; swapping selection swaps colors", () => {
  assert.equal(routeLineStyle("safe", "safe").color, "#1261ff");
  assert.equal(routeLineStyle("shortest", "safe").color, "#8b96a7");
  assert.ok(routeLineStyle("safe", "safe").zIndex - 1 > routeLineStyle("shortest", "safe").zIndex);
  assert.equal(routeLineStyle("safe", "shortest").color, "#8b96a7");
  assert.equal(routeLineStyle("shortest", "shortest").color, "#1261ff");
  assert.equal(routeLineStyle("safe", null).color, "#8b96a7");
});
test("route camera signature distinguishes new geometries with the same point count", () => {
  const route = (lon: number) => ({ route_type: "safe", route: { geometry: { coordinates: [[lon, 37.4], [126.7, 37.5]] } } }) as RouteCandidate;
  assert.notEqual(routeGeometrySignature([route(126.6)]), routeGeometrySignature([route(126.61)]));
});

test("overlapping lines prefer the selected route, while gray alternatives remain pickable", () => {
  for (const selected of ["safe", "shortest", "balanced"] as const) {
    assert.equal(routePickPriority(selected, selected), 6);
    assert.equal(routePickPriority(undefined, selected), 5);
    for (const other of ["safe", "shortest", "balanced"] as const) {
      if (other !== selected) assert.equal(routePickPriority(other, selected), 5);
    }
  }
  assert.equal(routePickPriority("safe", null), 5);
});
