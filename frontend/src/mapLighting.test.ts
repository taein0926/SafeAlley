import assert from "node:assert/strict";
import test from "node:test";
import { defaultStreetlightVisibility, mapLighting, STREETLIGHT_GLOW_IMAGE } from "./mapLighting.ts";

test("streetlights default off during day and on at night, respecting configured opt-out", () => {
  assert.equal(defaultStreetlightVisibility(false), false);
  assert.equal(defaultStreetlightVisibility(true), true);
  assert.equal(defaultStreetlightVisibility(false, false), false);
  assert.equal(defaultStreetlightVisibility(true, false), false);
});

test("basemap brightness is 100 percent by day and 50 percent at night", () => {
  const day = mapLighting(false);
  const night = mapLighting(true);
  assert.equal(day.brightness, 1);
  assert.equal(night.brightness, 0.5);
  assert.ok(night.brightness < day.brightness && night.brightness > 0.2);
  assert.ok(night.saturation < day.saturation);
  assert.ok(night.lightSize > day.lightSize);
  assert.ok(day.lightSize >= 24 && night.lightSize <= 40);
});

test("streetlights share a self-contained gradient with a bright circular core", () => {
  const svg = decodeURIComponent(STREETLIGHT_GLOW_IMAGE.split(",")[1]);
  assert.match(svg, /radialGradient/);
  assert.match(svg, /offset="1"[^>]*stop-opacity="0"/);
  assert.match(svg, /r="5" fill="#fffef2"/);
  assert.doesNotMatch(svg, /<filter|<animate|<script|<image/);
});
