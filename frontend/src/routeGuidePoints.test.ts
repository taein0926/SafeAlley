import assert from "node:assert/strict";
import test from "node:test";
import { CROSSING_GUIDE_IMAGE, SHOW_ALL_CROSSING_MARKERS, selectedRouteGuidePoints } from "./routeGuidePoints.ts";
import type { RouteCandidate, RouteRoadSegment, RouteType } from "./types.ts";

test("district-wide crossing inspection is disabled in normal map use", () => {
  assert.equal(SHOW_ALL_CROSSING_MARKERS, false);
});

test("crossing icon uses a round white badge and dark perspective stripes without external assets", () => {
  const svg = decodeURIComponent(CROSSING_GUIDE_IMAGE.split(",")[1]);
  assert.match(svg, /<circle[^>]+fill="#fff"[^>]+stroke="#555"/);
  assert.match(svg, /<path[^>]+fill="#383838"/);
  assert.match(svg, /width="96" height="96"/);
  assert.doesNotMatch(svg, /<rect|<image|<text|href=/);
});

const p = (x: number, y = 0) => [126.68 + x / (111_320 * Math.cos(37.46 * Math.PI / 180)), 37.46 + y / 111_320];
const segment = (coordinates: number[][], group: number | null = null) => ({ coordinates, crossing_group: group }) as RouteRoadSegment;
const candidate = (coordinates: number[][], segments: RouteRoadSegment[] = [], route_type: RouteType = "custom") => ({
  route_type, route: { geometry: { coordinates }, properties: { road_segments: segments } },
}) as RouteCandidate;

test("only the explicitly selected route contributes midpoint icons, including after a swap", () => {
  const custom = candidate([p(0), p(20), p(20, 30)], [segment([p(0), p(20)], 1)]);
  const shortest = candidate([p(0), p(0, 20), p(30, 20)], [segment([p(0), p(0, 20)], 2)], "shortest");
  const routes = [custom, shortest];
  assert.deepEqual(selectedRouteGuidePoints(routes, null), []);
  assert.deepEqual(selectedRouteGuidePoints(routes, "safe"), []);
  assert.equal(selectedRouteGuidePoints(routes, "custom")[0].longitude, p(10)[0]);
  assert.equal(selectedRouteGuidePoints(routes, "shortest")[0].latitude, p(0, 10)[1]);
});

test("straight road nodes and small geometry noise do not become turns", () => {
  const route = candidate([p(0), p(10, 0.3), p(20, -0.4), p(30), p(50)]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), []);
});

test("a right-angle turn without a crossing has no dot and keeps geometry unchanged", () => {
  const route = candidate([p(0), p(5), p(10), p(20), p(20, 5), p(20, 10), p(20, 25)]);
  const before = JSON.stringify(route);
  const dots = selectedRouteGuidePoints([route], "custom");
  assert.deepEqual(dots, []);
  assert.equal(JSON.stringify(route), before);
});

test("split crossing gets one midpoint icon, not endpoint dots", () => {
  const route = candidate([p(0), p(20), p(30), p(40), p(70)], [
    segment([p(0), p(20)]), segment([p(20), p(30)], 1),
    segment([p(30), p(40)], 1), segment([p(40), p(70)]),
  ]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom").map(d => d.longitude), [p(30)[0]]);
});

test("adjacent crossing groups each have one central icon", () => {
  const route = candidate([p(0), p(20), p(40), p(60), p(80)], [
    segment([p(20), p(40)], 1), segment([p(40), p(60)], 2),
  ]);
  assert.equal(selectedRouteGuidePoints([route], "custom").length, 2);
});

test("demo short third crossing gets a single central icon", () => {
  const entry = [126.6637352, 37.4704681];
  const exit = [126.6637172, 37.470459];
  const route = candidate([
    [126.6636111, 37.4701514], entry, exit, [126.6624096, 37.4718979],
  ], [segment([entry, exit], 43443)]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), [
    { longitude: (entry[0] + exit[0]) / 2, latitude: (entry[1] + exit[1]) / 2, kind: "crossing" },
  ]);
});

test("nearby but distinct crossings keep separate midpoint icons", () => {
  const route = candidate([p(0), p(20), p(22), p(24), p(26), p(50)], [
    segment([p(20), p(22)], 1), segment([p(24), p(26)], 2),
  ]);
  const icons = selectedRouteGuidePoints([route], "custom");
  assert.equal(icons.length, 2);
  [p(21)[0], p(25)[0]].forEach((lon, i) => assert.ok(Math.abs(icons[i].longitude - lon) < 1e-10));
});

test("curved crossing midpoint follows the path and zero-length crossings are omitted", () => {
  const route = candidate([p(0), p(10), p(30), p(30, 20), p(50, 20)], [
    segment([p(10), p(30)], 1), segment([p(30), p(30, 20)], 1),
    segment([p(50, 20), p(50, 20)], 2),
  ]);
  const before = JSON.stringify(route);
  const icons = selectedRouteGuidePoints([route], "custom");
  assert.equal(icons.length, 1);
  assert.ok(Math.abs(icons[0].longitude - p(30)[0]) < 1e-10);
  assert.ok(Math.abs(icons[0].latitude - p(30)[1]) < 1e-10);
  assert.equal(JSON.stringify(route), before);
});

test("crossing from route start gets its midpoint rather than a turn dot", () => {
  const route = candidate([p(0), p(20), p(20, 30)], [segment([p(0), p(20)], 1)]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), [{ longitude: p(10)[0], latitude: p(10)[1], kind: "crossing" }]);
});

test("missing crossing metadata never invents a crossing on a straight road", () => {
  const route = candidate([p(0), p(30)], [segment([p(0), p(30)])]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), []);
});

test("empty, invalid, and duplicated coordinates are safe", () => {
  for (const coordinates of [[], [p(0)], [p(0), [NaN, 37]], [p(0), p(0)]]) {
    assert.deepEqual(selectedRouteGuidePoints([candidate(coordinates)], "custom"), []);
  }
});
