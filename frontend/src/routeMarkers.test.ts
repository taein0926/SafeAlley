import assert from "node:assert/strict";
import test from "node:test";
import { ROUTE_MARKER_COLORS, routeMarkerImage, routeMarkerLocations } from "./routeMarkers.ts";
import type { RouteCandidate } from "./types.ts";

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
