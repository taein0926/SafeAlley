import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { errorFromApiDetail, PlaceSelectionRequiredError } from "./placeSelection.ts";

test("structured apartment ambiguity becomes a map-selection error", () => {
  const error = errorFromApiDetail({
    code: "building_selection_required",
    message: "원하는 동을 선택해 주세요.",
    target: "destination",
    place_name: "테스트아파트",
    focus: { west: 126.65, south: 37.45, east: 126.66, north: 37.46 },
  }, "fallback");
  assert.ok(error instanceof PlaceSelectionRequiredError);
  assert.equal(error.message, "원하는 동을 선택해 주세요.");
  assert.equal(error.target, "destination");
  assert.equal(error.placeName, "테스트아파트");
});

test("invalid structured details remain ordinary errors", () => {
  const error = errorFromApiDetail({
    code: "building_selection_required", message: "잘못된 범위",
    focus: { west: 127, south: 37.5, east: 126, north: 37.4 },
  }, "fallback");
  assert.equal(error.constructor, Error);
  assert.equal(error.message, "잘못된 범위");
});

test("apartment selection focuses the map and activates the requested endpoint", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const map = readFileSync(new URL("./components/CesiumRoadMap.tsx", import.meta.url), "utf8");
  assert.match(app, /setBuildingSelectionMode\(target\)/);
  assert.match(app, /setMapFocus\(error\.focus\)/);
  assert.match(app, /focusBounds=\{mapFocus\}/);
  assert.match(map, /Rectangle\.fromDegrees\(/);
  assert.match(map, /\[focusBounds\]/);
});
