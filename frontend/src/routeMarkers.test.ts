import assert from "node:assert/strict";
import test from "node:test";
import { ROUTE_MARKER_COLORS, routeMarkerImage } from "./routeMarkers.ts";

test("location buttons match the map's start/end colors and white circular outlines", () => {
  for (const kind of ["origin", "destination"] as const) {
    const svg = decodeURIComponent(routeMarkerImage(kind).split(",")[1]);
    assert.ok(svg.includes(`fill="${ROUTE_MARKER_COLORS[kind]}"`));
    assert.match(svg, /<circle/);
    assert.match(svg, /stroke="white" stroke-width="3"/);
  }
  assert.notEqual(routeMarkerImage("origin"), routeMarkerImage("destination"));
});
