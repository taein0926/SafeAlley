import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("map does not fetch or render inspection roads, while keeping routes and stairs", () => {
  const source = readFileSync(new URL("./components/CesiumRoadMap.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\/api\/osm-roads|pedestrian-overlay|pedestrianOverlay|refreshVisibleRoads|scheduleRoadRefresh/);
  assert.match(source, /recommended-route-/);
  assert.match(source, /\/api\/roads\?source=osm&steps_only=true/);
  assert.match(source, /selectedRouteGuidePoints/);
});
