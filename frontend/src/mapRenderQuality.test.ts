import assert from "node:assert/strict";
import test from "node:test";
import { MapRenderQuality, setRenderResolution, REST_RESOLUTION, MOVING_RESOLUTION, QUALITY_SETTLE_MS } from "./mapRenderQuality.ts";

test("odd-sized canvas rounding cannot change the camera projection on quality switches", () => {
  const width = 901, height = 721;
  const aspect = Math.floor(width * REST_RESOLUTION) / Math.floor(height * REST_RESOLUTION);
  let resizes = 0;
  const viewer = {
    resolutionScale: REST_RESOLUTION,
    camera: { frustum: { aspectRatio: aspect } },
    resize() {
      resizes++;
      this.camera.frustum.aspectRatio = Math.floor(width * this.resolutionScale) / Math.floor(height * this.resolutionScale);
    },
  };
  assert.notEqual(aspect, width / height); // Reproduces the previous false camera movement.
  for (let i = 0; i < 10; i++) {
    setRenderResolution(viewer, MOVING_RESOLUTION);
    assert.equal(viewer.camera.frustum.aspectRatio, aspect);
    setRenderResolution(viewer, REST_RESOLUTION);
    assert.equal(viewer.camera.frustum.aspectRatio, aspect);
  }
  assert.equal(setRenderResolution(viewer, REST_RESOLUTION), false);
  assert.equal(resizes, 20);
});

test("quality changes retain the latest real viewport aspect after window resize", () => {
  const viewer = { resolutionScale: REST_RESOLUTION, camera: { frustum: { aspectRatio: 1.7 } },
    resize() { this.camera.frustum.aspectRatio = 1.7001; } };
  setRenderResolution(viewer, MOVING_RESOLUTION);
  assert.equal(viewer.camera.frustum.aspectRatio, 1.7);
  viewer.camera.frustum.aspectRatio = 1.1;
  setRenderResolution(viewer, REST_RESOLUTION);
  assert.equal(viewer.camera.frustum.aspectRatio, 1.1);
});

test("initial quality, settle delay, and successive gestures are stable", () => {
  const quality = new MapRenderQuality();
  assert.equal(quality.simplified(0), false);
  quality.start();
  assert.equal(quality.simplified(100), true);
  quality.stop(100);
  assert.equal(quality.simplified(100 + QUALITY_SETTLE_MS - 1), true);
  quality.start();
  assert.equal(quality.simplified(10000), true);
  quality.stop(10000);
  assert.equal(quality.simplified(10000 + QUALITY_SETTLE_MS), false);
});
