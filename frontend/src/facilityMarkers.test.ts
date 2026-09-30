import assert from "node:assert/strict";
import test from "node:test";
import {
  CCTV_MARKER_IMAGE, POLICE_MARKER_IMAGE, FIRE_STATION_MARKER_IMAGE,
  HOSPITAL_MARKER_IMAGE, GENERIC_HELP_MARKER_IMAGE, helpPointMarkerImage,
} from "./facilityMarkers.ts";

test("each facility category selects its own shared icon", () => {
  assert.equal(helpPointMarkerImage("police"), POLICE_MARKER_IMAGE);
  assert.equal(helpPointMarkerImage("fire_station"), FIRE_STATION_MARKER_IMAGE);
  assert.equal(helpPointMarkerImage("emergency_medical"), HOSPITAL_MARKER_IMAGE);
  for (const category of [null, undefined, "unknown", {}, "__proto__"]) {
    assert.equal(helpPointMarkerImage(category), GENERIC_HELP_MARKER_IMAGE);
  }
});

test("CCTV uses a white circular badge and dark camera, distinct from cyan buildings", () => {
  const svg = decodeURIComponent(CCTV_MARKER_IMAGE.split(",")[1]);
  assert.match(svg, /<circle cx="22" cy="22" r="21" fill="#ffffff"/);
  assert.match(svg, /stroke="#65717c"/);
  assert.match(svg, /fill="#424b55"/);
  assert.match(svg, /rotate\(-25 22 22\)/);
  assert.doesNotMatch(svg, /#125363|#a5f1ff|opacity=/);
});

test("fire stations display white 119 digits on the red badge", () => {
  const svg = decodeURIComponent(FIRE_STATION_MARKER_IMAGE.split(",")[1]);
  assert.match(svg, /fill="#b63038"/);
  assert.match(svg, /aria-label="119"/);
  assert.match(svg, /stroke="white"/);
  assert.doesNotMatch(svg, /<text|<rect/);
});

test("all safety facilities use circular badges with inset pictograms", () => {
  for (const image of [POLICE_MARKER_IMAGE, FIRE_STATION_MARKER_IMAGE, HOSPITAL_MARKER_IMAGE, GENERIC_HELP_MARKER_IMAGE]) {
    const svg = decodeURIComponent(image.split(",")[1]);
    assert.match(svg, /<circle cx="22" cy="22" r="21"/);
    assert.match(svg, /translate\(3\.3 3\.3\) scale\(0\.85\)/);
    assert.doesNotMatch(svg, /<rect/);
  }
});

test("markers are distinct, self-contained SVG pictograms without font or network dependencies", () => {
  const images = [CCTV_MARKER_IMAGE, POLICE_MARKER_IMAGE, FIRE_STATION_MARKER_IMAGE,
    HOSPITAL_MARKER_IMAGE, GENERIC_HELP_MARKER_IMAGE];
  assert.equal(new Set(images).size, images.length);
  for (const image of images) {
    assert.ok(image.startsWith("data:image/svg+xml,"));
    const svg = decodeURIComponent(image.split(",")[1]);
    assert.match(svg, /viewBox="0 0 44 44"/);
    assert.match(svg, /<path /);
    assert.ok(svg.endsWith("</svg>"));
    assert.doesNotMatch(svg, /<text|<image|<script|<filter|<animate|href=/);
  }
});
