import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("map does not fetch or render inspection roads, while keeping routes and stairs", () => {
  const source = readFileSync(new URL("./components/CesiumRoadMap.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\/api\/osm-roads|pedestrian-overlay|pedestrianOverlay|refreshVisibleRoads|scheduleRoadRefresh/);
  assert.match(source, /recommended-route-/);
  assert.match(source, /\/api\/roads\?source=osm&steps_only=true/);
  assert.match(source, /selectedRouteGuidePoints/);
  assert.doesNotMatch(source, /\/api\/crossings|SHOW_ALL_CROSSING_MARKERS|allCrossingsReady|addCrossing/);
  assert.doesNotMatch(source, /createStreetlightDensityTexture/);
  assert.match(source, /\/api\/streetlight-heatmap\/manifest/);
  assert.match(source, /\/api\/pedestrian-bridges/);
});

test("route results do not render an unverified major-road review notice", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /현장 확인이 필요한 대로|unverified_major_road_count/);
});
