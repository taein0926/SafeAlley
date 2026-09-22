import assert from "node:assert/strict";
import test from "node:test";
import { bridgeMarkerPosition, CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE } from "./bridgeMarkers.ts";

test("bridge marker preserves supplied WGS84 location", () => {
  assert.deepEqual(bridgeMarkerPosition([126.686009, 37.46469947]), [126.686009, 37.46469947]);
});

test("invalid bridge locations are not placed at an invented point", () => {
  for (const point of [[], [126], [NaN, 37], [126, Infinity], [900000, 1900000], [126, 91]]) {
    assert.equal(bridgeMarkerPosition(point), null);
  }
});

test("connected and reference-only bridge markers are distinct font-independent icons", () => {
  assert.notEqual(CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE);
  for (const image of [CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE]) {
    assert.ok(image.startsWith("data:image/svg+xml,"));
    assert.ok(decodeURIComponent(image).includes("<path"));
  }
});
