import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { candidateFocusBounds, errorFromApiDetail, PlaceCandidatesRequiredError, PlaceSelectionRequiredError, resolveSelectedPlaces } from "./placeSelection.ts";

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

const university = (address: string) => ({
  name: "인천대학교", address, category: "building", source: "molit-gis-building", latitude: 37.47, longitude: 126.66,
});

test("candidate preview frames the exact coordinate without selecting a place", () => {
  const place = university("도화동 995");
  const before = { ...place };
  const bounds = candidateFocusBounds(place);
  assert.equal((bounds.west + bounds.east) / 2, place.longitude);
  assert.equal((bounds.south + bounds.north) / 2, place.latitude);
  assert.ok(bounds.east - bounds.west > 0.002, "Include surrounding streets instead of a building close-up");
  assert.ok(bounds.east - bounds.west < 0.004);
  assert.ok(bounds.north - bounds.south > 0.0015);
  assert.ok(bounds.north - bounds.south < 0.003);
  assert.notEqual(candidateFocusBounds(place), bounds, "Repeated previews trigger a new camera flight");
  assert.deepEqual(place, before);
});

test("distinct campus candidates are selectable without silently choosing one", () => {
  const error = errorFromApiDetail({ code: "place_selection_required", target: "destination", place_name: "인천대",
    message: "선택해 주세요", candidates: [university("도화동 995"), university("도화동 112-19")],
  }, "fallback");
  assert.ok(error instanceof PlaceCandidatesRequiredError);
  assert.equal(error.target, "destination");
  assert.equal(error.candidates.length, 2);
  assert.equal(error.candidates[1].address, "도화동 112-19");
});

test("invalid candidate coordinates do not become selectable", () => {
  const error = errorFromApiDetail({ code: "place_selection_required", candidates: [university("995"),
    { ...university("112-19"), latitude: 100 }], message: "invalid",
  }, "fallback");
  assert.equal(error.constructor, Error);
});

test("AI continuation keeps the selected campus and only resolves the other endpoint", async () => {
  const interpretation = { origin_name: "서화초", destination_name: "인천대", departure_time: "20:00:00", profile: "pedestrian" as const,
    preferences: [{ factor: "stairs_distance_m", direction: "avoid" as const, weight: 1 }] };
  const selected = university("도화동 995");
  const calls: string[] = [];
  const result = await resolveSelectedPlaces(interpretation, { destination: selected }, async name => {
    calls.push(name);
    return { ...university("서화초 주소"), name: "인천서화초등학교" };
  });
  assert.deepEqual(calls, ["서화초"]);
  assert.equal(result.destination, selected);
  assert.equal(interpretation.departure_time, "20:00:00");
  assert.equal(interpretation.preferences[0].direction, "avoid");
});

test("another ambiguous endpoint is labelled correctly during AI continuation", async () => {
  const error = new PlaceCandidatesRequiredError("선택", [university("995"), university("112-19")]);
  const interpretation = { origin_name: "서화초", destination_name: "인천대", departure_time: null, profile: "pedestrian" as const, preferences: [] };
  await assert.rejects(resolveSelectedPlaces(interpretation, { destination: university("995") }, async () => { throw error; }),
    (failure: unknown) => failure instanceof PlaceCandidatesRequiredError && failure.target === "origin");
});
