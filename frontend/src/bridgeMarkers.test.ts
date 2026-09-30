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

test("all bridge markers share the stair palette and font-independent circular icon", () => {
  assert.equal(CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE);
  for (const image of [CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE]) {
    assert.ok(image.startsWith("data:image/svg+xml,"));
    assert.ok(decodeURIComponent(image).includes("<path"));
    const svg = decodeURIComponent(image.split(",")[1]);
    assert.match(svg, /fill="#ffffff"/);
    assert.match(svg, /stroke="#34495e"/);
    assert.match(svg, /stroke="#52677d"/);
    assert.match(svg, /<circle cx="22" cy="22" r="21"/);
    assert.doesNotMatch(svg, /<rect/);
    assert.match(svg, /translate\(4\.4 4\.4\) scale\(0\.8\)/);
    assert.match(svg, /M5 33h5v-6h5v-6h14v6h5v6h5/);
    assert.doesNotMatch(svg, /<text|<image|<script/);
  }
});
