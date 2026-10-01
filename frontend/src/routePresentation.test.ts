import assert from "node:assert/strict";
import test from "node:test";
import { routeCapPath, routeEndCaps, routeLineStyle, routeGeometrySignature, routePickPriority } from "./routePresentation.ts";
import type { RouteCandidate } from "./types.ts";

test("routes retain their width with a thin colored casing in both themes", () => {
  assert.equal(routeLineStyle("custom", "custom").width, 9);
  assert.equal(routeLineStyle("custom", "custom").casingWidth, 12);
  assert.equal(routeLineStyle("shortest", "custom").width, 6);
  assert.equal(routeLineStyle("shortest", "custom").casingWidth, 8);
  assert.equal(routeLineStyle("custom", "custom", false).casingColor, "#0054bb");
  assert.equal(routeLineStyle("custom", "custom", true).casingColor, "#0054bb");
  assert.equal(routeLineStyle("shortest", "custom").casingColor, "#707987");
});

test("active route is blue above the gray alternative; swapping selection swaps colors", () => {
  assert.equal(routeLineStyle("safe", "safe").color, "#007aff");
  assert.equal(routeLineStyle("shortest", "safe").color, "#89919d");
  assert.ok(routeLineStyle("safe", "safe").zIndex - 1 > routeLineStyle("shortest", "safe").zIndex);
  assert.equal(routeLineStyle("safe", "shortest").color, "#89919d");
  assert.equal(routeLineStyle("shortest", "shortest").color, "#007aff");
  assert.equal(routeLineStyle("safe", null).color, "#89919d");
});

test("round end caps skip repeated points, preserve geometry and draw selection last", () => {
  const candidate = (type: string, coordinates: number[][]) => ({ route_type: type, route: { geometry: { coordinates } } }) as RouteCandidate;
  const routes = [candidate("custom", [[1,2],[1,2],[3,4],[3,4]]), candidate("shortest", [[5,6],[7,8]])];
  const before = JSON.stringify(routes);
  const caps = routeEndCaps(routes, "custom");
  assert.equal(caps.length, 4);
  assert.deepEqual(caps[2], { routeType: "custom", position: [1,2], neighbor: [3,4] });
  assert.deepEqual(caps[3], { routeType: "custom", position: [3,4], neighbor: [1,2] });
  assert.equal(JSON.stringify(routes), before);
  assert.deepEqual(routeEndCaps([candidate("custom", []), candidate("shortest", [[1,2],[1,2]])], "custom"), []);
  assert.equal(routeCapPath(12), "M 0 -6 A 6 6 0 0 1 0 6 Z");
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
