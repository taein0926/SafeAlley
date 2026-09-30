import assert from "node:assert/strict";
import test from "node:test";
import { ROUTE_MARKER_COLORS, routeMarkerImage, routeMarkerLocations, selectedRouteLabelLocation } from "./routeMarkers.ts";
import type { RouteCandidate } from "./types.ts";

test("route sign follows the selected path midpoint, not the bbox or vertex count", () => {
  const candidate = (route_type: "custom" | "shortest", coordinates: number[][]) => ({ route_type, route: { geometry: { coordinates } } }) as RouteCandidate;
  const routes = [candidate("custom", [[126, 37], [126, 37.001], [126, 37.01]]),
    candidate("shortest", [[127, 37], [127, 37.001], [127.002, 37.001]])];
  const before = JSON.stringify(routes);
  const customPoint = selectedRouteLabelLocation(routes, "custom")!;
  assert.equal(customPoint.longitude, 126);
  assert.ok(Math.abs(customPoint.latitude - 37.005) < 1e-10);
  const point = selectedRouteLabelLocation(routes, "shortest")!;
  assert.equal(point.latitude, 37.001);
  assert.ok(point.longitude > 127 && point.longitude < 127.002);
  assert.equal(selectedRouteLabelLocation(routes, null), null);
  assert.equal(selectedRouteLabelLocation(routes, "safe"), null);
  assert.equal(JSON.stringify(routes), before);
  for (const c of [[], [[126, 37]], [[126, 37], [NaN, 37]], [[126, 37], [126, 37]]]) {
    assert.equal(selectedRouteLabelLocation([candidate("custom", c)], "custom"), null);
  }
});

test("map and input pins share labelled start/end silhouettes and colors", () => {
  for (const kind of ["origin", "destination"] as const) {
    const svg = decodeURIComponent(routeMarkerImage(kind).split(",")[1]);
    assert.ok(svg.includes(ROUTE_MARKER_COLORS[kind]));
    assert.match(svg, /viewBox="0 0 40 50"/);
    assert.match(svg, /width="160" height="200"/);
    assert.match(svg, /<path/);
    assert.match(svg, /stroke="white"/);
    assert.ok(svg.includes(kind === "origin" ? "출발" : "도착"));
    assert.doesNotMatch(svg, /<image|href=/);
  }
  assert.notEqual(routeMarkerImage("origin"), routeMarkerImage("destination"));
});

test("vector pins follow selected route endpoints, with drafts only before a result", () => {
  const candidate = (route_type: "custom" | "shortest", x: number) => ({route_type, route: {geometry: {coordinates: [[x, 37.4], [126.7, 37.5]]}}}) as RouteCandidate;
  const routes = [candidate("custom", 126.5), candidate("shortest", 126.6)];
  const drafts = [{kind: "origin" as const, longitude: 126.4, latitude: 37.3}];
  assert.equal(routeMarkerLocations(routes, "shortest", drafts)[0].longitude, 126.6);
  assert.equal(routeMarkerLocations(routes, null, drafts)[0].longitude, 126.5);
  assert.equal(routeMarkerLocations(routes, "custom", drafts)[1].kind, "destination");
  assert.deepEqual(routeMarkerLocations([], null, drafts), drafts);
  assert.deepEqual(routeMarkerLocations([], null, [{...drafts[0], longitude: NaN}]), []);
  assert.deepEqual(routeMarkerLocations([], null, []), []);
});
