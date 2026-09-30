import assert from "node:assert/strict";
import test from "node:test";
import { facilityToggleImage } from "./facilityToggleIcons.ts";

test("all facility controls are transparent pictograms with a shared size and stroke", () => {
  const images = ["streetlights", "cctvs", "helpPoints", "stairsAndBridges"].map(kind => facilityToggleImage(kind as Parameters<typeof facilityToggleImage>[0]));
  assert.equal(new Set(images).size, 4);
  for (const image of images) {
    const svg = decodeURIComponent(image.split(",")[1]);
    assert.match(svg, /width="96" height="96" viewBox="0 0 44 44"/);
    assert.doesNotMatch(svg, /<circle|<rect|#ffffff|#52677d/);
    assert.match(svg, /stroke="#34495e" stroke-width="2.5"/);
    assert.doesNotMatch(svg, /<text|<image|href=/);
  }
});
