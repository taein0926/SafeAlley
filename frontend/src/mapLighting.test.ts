import assert from "node:assert/strict";
import test from "node:test";
import { mapLighting, STREETLIGHT_GLOW_IMAGE } from "./mapLighting.ts";

test("day basemap is subdued and night is darker with stronger light markers", () => {
  const day = mapLighting(false);
  const night = mapLighting(true);
  assert.ok(day.brightness < 1 && day.brightness > 0.5);
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
