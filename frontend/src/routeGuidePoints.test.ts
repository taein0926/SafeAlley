import assert from "node:assert/strict";
import test from "node:test";
import { selectedRouteGuidePoints } from "./routeGuidePoints.ts";
import type { RouteCandidate, RouteRoadSegment, RouteType } from "./types.ts";

const p = (x: number, y = 0) => [126.68 + x / (111_320 * Math.cos(37.46 * Math.PI / 180)), 37.46 + y / 111_320];
const segment = (coordinates: number[][], group: number | null = null) => ({ coordinates, crossing_group: group }) as RouteRoadSegment;
const candidate = (coordinates: number[][], segments: RouteRoadSegment[] = [], route_type: RouteType = "custom") => ({
  route_type, route: { geometry: { coordinates }, properties: { road_segments: segments } },
}) as RouteCandidate;

test("only the explicitly selected route contributes dots, including after a swap", () => {
  const custom = candidate([p(0), p(20), p(20, 30)], [segment([p(0), p(20)], 1)]);
  const shortest = candidate([p(0), p(0, 20), p(30, 20)], [segment([p(0), p(0, 20)], 2)], "shortest");
  const routes = [custom, shortest];
  assert.deepEqual(selectedRouteGuidePoints(routes, null), []);
  assert.deepEqual(selectedRouteGuidePoints(routes, "safe"), []);
  assert.equal(selectedRouteGuidePoints(routes, "custom")[0].longitude, p(20)[0]);
  assert.equal(selectedRouteGuidePoints(routes, "shortest")[0].latitude, p(0, 20)[1]);
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

test("split crossing gets entry and exit dots, not internal segment dots", () => {
  const route = candidate([p(0), p(20), p(30), p(40), p(70)], [
    segment([p(0), p(20)]), segment([p(20), p(30)], 1),
    segment([p(30), p(40)], 1), segment([p(40), p(70)]),
  ]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom").map(d => d.longitude), [p(20)[0], p(40)[0]]);
});

test("adjacent crossing groups keep their shared landing only once", () => {
  const route = candidate([p(0), p(20), p(40), p(60), p(80)], [
    segment([p(20), p(40)], 1), segment([p(40), p(60)], 2),
  ]);
  assert.equal(selectedRouteGuidePoints([route], "custom").length, 3);
});

test("demo third crossing retains both ends 1.89m apart at their actual coordinates", () => {
  const entry = [126.6637352, 37.4704681];
  const exit = [126.6637172, 37.470459];
  const route = candidate([
    [126.6636111, 37.4701514], entry, exit, [126.6624096, 37.4718979],
  ], [segment([entry, exit], 43443)]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), [
    { longitude: entry[0], latitude: entry[1], kind: "crossing" },
    { longitude: exit[0], latitude: exit[1], kind: "crossing" },
  ]);
});

test("nearby but distinct crossing ends are never merged across groups", () => {
  const route = candidate([p(0), p(20), p(22), p(24), p(26), p(50)], [
    segment([p(20), p(22)], 1), segment([p(24), p(26)], 2),
  ]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom").map(d => d.longitude),
    [p(20)[0], p(22)[0], p(24)[0], p(26)[0]]);
});

test("crossing at a turn is one dot and endpoint pins do not get duplicate dots", () => {
  const route = candidate([p(0), p(20), p(20, 30)], [segment([p(0), p(20)], 1)]);
  assert.deepEqual(selectedRouteGuidePoints([route], "custom"), [{ longitude: p(20)[0], latitude: p(20)[1], kind: "crossing" }]);
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
