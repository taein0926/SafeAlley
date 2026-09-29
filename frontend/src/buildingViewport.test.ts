import assert from "node:assert/strict";
import test from "node:test";
import { buildingRequestBounds, BuildingViewportRequests, geometryBounds, boundsIntersect, routeBuildingTiles, MAX_ROUTE_BUILDING_TILES } from "./buildingViewport.ts";
import type { BuildingRequest } from "./buildingViewport.ts";

const view = { west: 126.6765, south: 37.461, east: 126.6815, north: 37.465 };
const east = { ...view, west: view.west + 0.004, east: view.east + 0.004 };
const far = { ...view, west: view.west + 0.08, east: view.east + 0.08 };
function finish(cache: BuildingViewportRequests, request: BuildingRequest) {
  for (const batch of request.batches) assert.equal(cache.commit(request, batch), true);
}
function load(cache: BuildingViewportRequests, extent = view) {
  const decision = cache.plan(extent);
  assert.ok(decision.kind === "load");
  return decision.request;
}

test("invalid/city views skip detailed buildings; station view is allowed", () => {
  for (const v of [null, { ...view, east: view.west }, { ...view, north: Infinity }, { ...view, east: view.east + 0.1 }]) assert.equal(buildingRequestBounds(v), null);
  assert.ok(buildingRequestBounds({ west: 126.6709, east: 126.6899, south: 37.461, north: 37.469 }));
});

test("initial adjacent tiles share one request; same view never refetches", () => {
  const cache = new BuildingViewportRequests();
  const first = load(cache);
  assert.equal(first.batches.length, 1);
  assert.equal(cache.plan(view).kind, "pending");
  finish(cache, first);
  assert.equal(cache.plan(view).kind, "reuse");
});

test("panning requests only new tiles, leaving loaded tiles intact", () => {
  const cache = new BuildingViewportRequests();
  const first = load(cache);
  const oldKeys = new Set(first.batches.flatMap((batch) => batch.tiles.map((tile) => tile.key)));
  finish(cache, first);
  const second = load(cache, east);
  const newTiles = second.batches.flatMap((batch) => batch.tiles);
  assert.ok(newTiles.length < oldKeys.size);
  for (const tile of newTiles) assert.equal(oldKeys.has(tile.key), false);
  for (const batch of second.batches) for (const old of first.batches.flatMap((item) => item.tiles)) {
    const overlapX = Math.min(old.bounds.east, batch.bounds.east) - Math.max(old.bounds.west, batch.bounds.west);
    const overlapY = Math.min(old.bounds.north, batch.bounds.north) - Math.max(old.bounds.south, batch.bounds.south);
    assert.ok(overlapX <= 0 || overlapY <= 0);
  }
  finish(cache, second);
  assert.equal(cache.plan(view).kind, "reuse");
});

test("zoom out hides geometry but zooming back reuses cache", () => {
  const cache = new BuildingViewportRequests();
  finish(cache, load(cache));
  assert.equal(cache.plan(null).kind, "hidden");
  assert.equal(cache.visible.size, 0);
  assert.equal(cache.plan(view).kind, "reuse");
});

test("stale responses cannot commit after a new request or teardown", () => {
  const cache = new BuildingViewportRequests();
  const old = load(cache);
  const current = load(cache, far);
  assert.equal(old.controller.signal.aborted, true);
  assert.equal(cache.commit(old, old.batches[0]), false);
  cache.fail(old);
  assert.equal(cache.isCurrent(current), true);
  cache.clear();
  assert.equal(cache.commit(current, current.batches[0]), false);
});

test("cache evicts only old offscreen tiles and refetches them when revisited", () => {
  const cache = new BuildingViewportRequests(4);
  finish(cache, load(cache));
  finish(cache, load(cache, far));
  const removed = cache.evict();
  assert.ok(removed.length > 0);
  assert.ok(removed.every((key) => !cache.visible.has(key)));
  assert.equal(cache.plan(far).kind, "reuse");
  assert.equal(cache.plan(view).kind, "load");
});

test("a failed new region does not invalidate old cached regions", () => {
  const cache = new BuildingViewportRequests();
  finish(cache, load(cache));
  cache.fail(load(cache, east));
  assert.equal(cache.plan(view).kind, "reuse");
});

test("cancelling a multi-batch load retains batches already committed", () => {
  const cache = new BuildingViewportRequests();
  finish(cache, load(cache));
  const diagonal = { west: view.west + 0.004, east: view.east + 0.004, south: view.south + 0.004, north: view.north + 0.004 };
  const request = load(cache, diagonal);
  assert.ok(request.batches.length > 1);
  const first = request.batches[0];
  assert.equal(cache.commit(request, first), true);
  cache.cancelPending();
  assert.equal(cache.commit(request, request.batches[1]), false);
  const retry = load(cache, diagonal);
  const finishedKeys = new Set(first.tiles.map((tile) => tile.key));
  assert.ok(retry.batches.every((batch) => batch.tiles.every((tile) => !finishedKeys.has(tile.key))));
});

test("polygon bounds support multi-polygons and buildings on tile boundaries", () => {
  const bounds = geometryBounds([[[[126.68, 37.46], [126.684, 37.464]]]]);
  assert.deepEqual(bounds, { west: 126.68, east: 126.684, south: 37.46, north: 37.464 });
  assert.ok(boundsIntersect(bounds!, { west: 126.684, east: 126.688, south: 37.46, north: 37.464 }));
  assert.equal(geometryBounds([]), null);
});

const overview = { west: 126.65, east: 126.72, south: 37.43, north: 37.48 };
const route = [[126.661, 37.441], [126.701, 37.469]];

test("zoomed-out route loads bounded single-tile batches and reuses them", () => {
  const cache = new BuildingViewportRequests(32);
  assert.equal(cache.plan(overview).kind, "hidden");
  const decision = cache.plan(overview, route);
  assert.equal(cache.routeFocused, true);
  assert.ok(decision.kind === "load");
  assert.ok(decision.request.batches.length > 1);
  assert.ok(decision.request.batches.length <= MAX_ROUTE_BUILDING_TILES);
  assert.ok(decision.request.batches.every((batch) => batch.tiles.length === 1));
  assert.equal(cache.plan(overview, route).kind, "pending");
  finish(cache, decision.request);
  assert.equal(cache.plan(overview, route).kind, "reuse");
  cache.plan(view, route);
  assert.equal(cache.routeFocused, false);
});

test("route corridor includes endpoints and intermediate geometry, not just vertices", () => {
  const tiles = routeBuildingTiles(overview, route);
  assert.ok(tiles.length <= MAX_ROUTE_BUILDING_TILES);
  for (const [x, y] of [...route, [126.681, 37.455]]) {
    assert.ok(tiles.some(({ bounds }) => x >= bounds.west && x <= bounds.east && y >= bounds.south && y <= bounds.north));
  }
  assert.ok(tiles.every(({ bounds }) => boundsIntersect(bounds, overview)));
});

test("very long routes remain bounded and retain both ends", () => {
  const extent = { west: 126.5, east: 126.75, south: 37.4, north: 37.6 };
  const longRoute = [[126.501, 37.401], [126.749, 37.599]];
  const tiles = routeBuildingTiles(extent, longRoute);
  assert.equal(tiles.length, MAX_ROUTE_BUILDING_TILES);
  for (const [x, y] of longRoute) assert.ok(tiles.some(({ bounds }) => x >= bounds.west && x <= bounds.east && y >= bounds.south && y <= bounds.north));
});

test("route change cancels stale building batches; invalid or offscreen routes stay hidden", () => {
  const cache = new BuildingViewportRequests();
  const first = cache.plan(overview, route);
  assert.ok(first.kind === "load");
  const second = cache.plan(overview, [[126.705, 37.431], [126.717, 37.433]]);
  assert.ok(second.kind === "load");
  assert.equal(first.request.controller.signal.aborted, true);
  assert.equal(cache.commit(first.request, first.request.batches[0]), false);
  for (const invalid of [[], [[NaN, 37], [126, 37]], [[126.9, 37.6], [126.95, 37.65]]]) {
    assert.deepEqual(routeBuildingTiles(overview, invalid), []);
  }
  assert.deepEqual(routeBuildingTiles({ ...overview, east: 130 }, route), []);
  assert.deepEqual(routeBuildingTiles(null, route), []);
});
