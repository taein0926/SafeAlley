import assert from "node:assert/strict";
import test from "node:test";
import { FacilityViewportCache, facilityBounds, type FacilityRequest } from "./facilityViewport.ts";

const view = { west: 126.662, south: 37.462, east: 126.668, north: 37.468 };
const point = { id: 1, geometry: { type: "Point", coordinates: [126.665, 37.465] }, properties: {} };
function complete(cache: FacilityViewportCache, request: FacilityRequest) {
  for (const batch of request.batches) assert.equal(cache.commit(request, batch, [point]), true);
}
test("initial viewport batches tiles; empty/loaded tiles are cached and pending calls deduplicated", () => {
  const cache = new FacilityViewportCache();
  const request = cache.plan(view)!;
  assert.equal(request.batches.length, 1);
  assert.equal(cache.plan(view), null);
  assert.equal(request.controller.signal.aborted, false);
  complete(cache, request);
  assert.equal(cache.plan(view), null);
  assert.deepEqual(cache.features(), [point]);
});
test("pan fetches only new tiles, returning reuses cached data", () => {
  const cache = new FacilityViewportCache();
  const first = cache.plan(view)!;
  const keys = new Set(first.batches.flatMap(b => b.tiles.map(t => t.key)));
  complete(cache, first);
  const next = cache.plan({ ...view, east: 126.678 })!;
  for (const b of next.batches) for (const t of b.tiles) assert.equal(keys.has(t.key), false);
  complete(cache, next);
  assert.equal(cache.plan(view), null);
});
test("stale responses cannot cache tiles after moving or disabling a layer", () => {
  const cache = new FacilityViewportCache();
  const first = cache.plan(view)!;
  cache.plan(null);
  assert.equal(first.controller.signal.aborted, true);
  assert.equal(cache.commit(first, first.batches[0], [point]), false);
  assert.deepEqual(cache.features(), []);
  assert.ok(cache.plan(view));
});
test("boundary records deduplicate and failed requests can retry", () => {
  const cache = new FacilityViewportCache();
  const request = cache.plan({ ...view, east: 126.672 })!;
  const boundary = { ...point, geometry: { type: "Point", coordinates: [126.67, 37.465] } };
  for (const b of request.batches) cache.commit(request, b, [boundary]);
  assert.equal(cache.features().length, 1);
  const failed = cache.plan({ ...view, east: 126.688 })!;
  cache.fail(failed);
  assert.ok(cache.plan({ ...view, east: 126.688 }));
});
test("LRU evicts distant tiles, offscreen records do not become map objects", () => {
  const cache = new FacilityViewportCache(4);
  complete(cache, cache.plan(view)!);
  for (let i = 1; i < 10; i++) {
    const moved = { ...view, west: view.west + i * .03, east: view.east + i * .03 };
    complete(cache, cache.plan(moved)!);
    assert.deepEqual(cache.features(), []);
  }
  assert.ok(cache.cachedTileCount <= 4);
  assert.ok(cache.plan(view));
});
test("heatmap kernel buffer and invalid/district zoom bounds are limited", () => {
  const tiny = { west: 126.665, east: 126.6651, south: 37.465, north: 37.4651 };
  assert.ok(facilityBounds(tiny)!.west <= tiny.west - .001);
  for (const invalid of [null, { ...view, east: NaN }, { ...view, east: view.west }, { ...view, east: view.east + 1 }]) {
    assert.equal(facilityBounds(invalid), null);
  }
});
