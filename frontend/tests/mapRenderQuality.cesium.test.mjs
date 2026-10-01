// Run with dependencies installed: node --experimental-strip-types --test tests/*.cesium.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import Camera from "../node_modules/@cesium/engine/Source/Scene/Camera.js";
import View from "../node_modules/@cesium/engine/Source/Scene/View.js";
import GeographicProjection from "../node_modules/@cesium/engine/Source/Core/GeographicProjection.js";
import { setRenderResolution } from "../src/mapRenderQuality.ts";
import { BuildingViewportRequests } from "../src/buildingViewport.ts";

test("canvas quality resize is registered before scene rendering, never after a completed frame", () => {
  const component = readFileSync(new URL("../src/components/CesiumRoadMap.tsx", import.meta.url), "utf8");
  // Guard the production wiring, not only the math helper. Changing this phase
  // to postRender clears the frame immediately before the browser presents it.
  assert.match(component, /const removeQualityRender = viewer\.scene\.preUpdate\.addEventListener/);
  assert.doesNotMatch(component, /const removeQualityRender = viewer\.scene\.postRender\.addEventListener/);
});

function fixture() {
  const width = 901, height = 721;
  const scene = { drawingBufferWidth: Math.floor(width * 1.25), drawingBufferHeight: Math.floor(height * 1.25),
    mapProjection: new GeographicProjection(), cameraEventWaitTime: 0 };
  const camera = new Camera(scene);
  const state = { camera, _cameraClone: Camera.clone(camera), _cameraStartFired: false, _cameraMovedTime: 0 };
  const viewer = { camera, resolutionScale: 1.25,
    resize() { camera.frustum.aspectRatio = Math.floor(width * this.resolutionScale) / Math.floor(height * this.resolutionScale); } };
  const cache = new BuildingViewportRequests();
  const decision = cache.plan({ west: 126.656, south: 37.464, east: 126.672, north: 37.476 });
  assert.equal(decision.kind, "load");
  let starts = 0;
  camera.moveStart.addEventListener(() => { starts++; cache.cancelPending(); });
  return { viewer, cache, request: decision.request, starts: () => starts,
    tick: () => View.prototype.checkForCameraUpdates.call(state, scene),
    settle: () => { state._cameraMovedTime = 0; View.prototype.checkForCameraUpdates.call(state, scene); } };
}

test("previous resize behavior reproduces false movement and canceled building load in Cesium 1.133", () => {
  const f = fixture();
  assert.equal(f.tick(), false);
  f.viewer.resolutionScale = 1; f.viewer.resize();
  assert.equal(f.tick(), true);
  assert.equal(f.starts(), 1);
  assert.equal(f.request.controller.signal.aborted, true);
});

test("quality round trips no longer trigger movement or abort pending building data", () => {
  const f = fixture();
  for (let i = 0; i < 10; i++) {
    setRenderResolution(f.viewer, 1);
    assert.equal(f.tick(), false);
    setRenderResolution(f.viewer, 1.25);
    assert.equal(f.tick(), false);
  }
  assert.equal(f.starts(), 0);
  assert.equal(f.cache.isCurrent(f.request), true);
  for (const batch of f.request.batches) assert.equal(f.cache.commit(f.request, batch), true);
  // Real movement still starts the normal viewport lifecycle.
  f.viewer.camera.position.x += 10;
  assert.equal(f.tick(), true);
  assert.equal(f.starts(), 1);
});
