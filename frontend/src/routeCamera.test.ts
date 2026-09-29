import assert from "node:assert/strict";
import test from "node:test";
import { routeCameraFrame, routeCameraHeading, routeCameraTargetOffset, ROUTE_CAMERA_PITCH } from "./routeCamera.ts";

test("route camera is oblique and keeps short routes at a usable distance", () => {
  assert.ok(ROUTE_CAMERA_PITCH > -Math.PI / 2 && ROUTE_CAMERA_PITCH < -Math.PI / 4);
  assert.ok(routeCameraFrame([], 1668, 970, .65, 416).range >= 280);
});

test("actual route fits tightly outside the result panel for every heading", () => {
  for (const [width, height, inset] of [[1668, 970, 416], [900, 768, 416], [1280, 800, 0]]) {
    for (const heading of [0, Math.PI / 2, Math.PI, 4]) {
      const fovY = .65;
      const points = [{ x: -350, y: -1400, z: 0 }, { x: 600, y: 0, z: -2 }, { x: 250, y: 1700, z: 0 }];
      const { range, rightOffset, upOffset } = routeCameraFrame(points, width, height, fovY, inset, heading);
      const tanY = Math.tan(fovY / 2), tanX = tanY * width / height;
      const screens = points.map(({ x, y, z }) => {
        const forward = x * Math.sin(heading) + y * Math.cos(heading);
        const right = x * Math.cos(heading) - y * Math.sin(heading);
        const up = forward * Math.sin(-ROUTE_CAMERA_PITCH) + z * Math.cos(-ROUTE_CAMERA_PITCH);
        const depth = range + forward * Math.cos(-ROUTE_CAMERA_PITCH) - z * Math.sin(-ROUTE_CAMERA_PITCH);
        return { x: (1 + (right - rightOffset) / (depth * tanX)) * width / 2, y: (1 - (up - upOffset) / (depth * tanY)) * height / 2 };
      });
      for (const { x, y } of screens) {
        assert.ok(x >= inset + 36 - 1e-6 && x <= width - 36 + 1e-6);
        assert.ok(y >= 36 - 1e-6 && y <= height - 36 + 1e-6);
      }
      const spanX = Math.max(...screens.map((p) => p.x)) - Math.min(...screens.map((p) => p.x));
      const spanY = Math.max(...screens.map((p) => p.y)) - Math.min(...screens.map((p) => p.y));
      assert.ok(spanX / (width - inset - 72) > .99 || spanY / (height - 72) > .99);
    }
  }
});

test("larger routes zoom out; panel-free views need no sideways offset", () => {
  const points = (r: number) => [{ x: -r, y: 0, z: 0 }, { x: r, y: 0, z: 0 }];
  assert.ok(routeCameraFrame(points(1000), 1000, 800, .65, 416).range > routeCameraFrame(points(100), 1000, 800, .65, 416).range);
  assert.equal(routeCameraFrame(points(100), 1000, 800, .65).rightOffset, 0);
});

test("3D heading looks from start towards destination, including reversed routes", () => {
  for (const [end, expected] of [ [[0, 1], 0], [[1, 0], Math.PI / 2], [[0, -1], Math.PI], [[-1, 0], 3 * Math.PI / 2] ] as const) {
    assert.ok(Math.abs(routeCameraHeading([[0, 0], [...end]]) - expected) < 1e-10);
  }
  assert.equal(routeCameraHeading([[126.68, 37.46], [126.68, 37.45]]), Math.PI);
  assert.equal(routeCameraHeading([[126.68, 37.45], [126.68, 37.46]]), 0);
  assert.equal(routeCameraHeading([]), 0);
  assert.equal(routeCameraHeading([[126, 37], [126, 37]]), 0);
  assert.ok(Math.abs(routeCameraHeading([[0, 0], [1, 0], [0, 0]]) - Math.PI / 2) < 1e-10);
});

test("panel avoidance offset stays to camera-left for every route heading", () => {
  for (const heading of [0, Math.PI / 4, Math.PI / 2, Math.PI, 3 * Math.PI / 2]) {
    const offset = routeCameraTargetOffset(-150, heading);
    const cameraRight = offset.east * Math.cos(heading) - offset.north * Math.sin(heading);
    const forward = offset.east * Math.sin(heading) + offset.north * Math.cos(heading);
    assert.ok(Math.abs(cameraRight + 150) < 1e-10);
    assert.ok(Math.abs(forward) < 1e-10);
  }
});
