import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDirectRouteToolCall,
  currentLocalTime,
  estimatedWalkingMinutes,
  isValidDepartureTime,
  resolveDirectLocation,
  selectDisplayedCandidates,
  sliderToUnit,
} from "./routeSearch.ts";
import type { ResolvedPlace, RouteCandidate, RouteType } from "./types.ts";


const origin: ResolvedPlace = {
  name: "주안역",
  category: "subway_station",
  address: null,
  source: "test",
  latitude: 37.46,
  longitude: 126.68,
};
const destination = { ...origin, name: "인하대학교", latitude: 37.45 };

function candidate(routeType: RouteType): RouteCandidate {
  const routeIndex = { shortest: 1, balanced: 2, safe: 3 }[routeType];
  return {
    route_type: routeType,
    preference_score: 80,
    metrics: { safety_score: 70 },
    route: {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[126.68, 37.46], [126.69, 37.45 + routeIndex * 0.001]] },
      properties: {
        route_type: routeType,
        total_distance_m: 100,
        average_safety_score: 70,
        total_cost: 120,
        stairs_segment_count: 0,
        total_crosswalk_count: 0,
        stairs_distance_m: 0,
        sidewalk_coverage_percent: 100,
        max_slope_percent: null,
        slope_coverage_percent: 0,
        review_status: "map_data_only",
        unverified_major_road_count: 0,
        unverified_major_road_source_ids: [],
        road_segments: [{
          id: routeIndex,
          source_id: `segment-${routeIndex}`,
          name: null,
          distance_m: 100,
          streetlight_score: 70,
          cctv_score: 70,
          population_score: 70,
          safety_score: 70,
          coordinates: [[126.68, 37.46], [126.69, 37.45 + routeIndex * 0.001]],
          highway: "residential",
          is_steps: false,
        }],
      },
    },
  };
}

test("0-100 slider values map to the backend stairs range", () => {
  assert.equal(sliderToUnit(0), 0);
  assert.equal(sliderToUnit(65), 0.65);
  assert.equal(sliderToUnit(100), 1);
});

test("walking estimate uses distance, not routing cost", () => {
  assert.equal(estimatedWalkingMinutes(312), 5);
  assert.equal(estimatedWalkingMinutes(4500), 60);
  assert.equal(estimatedWalkingMinutes(0), 0);
  assert.equal(estimatedWalkingMinutes(-1), null);
  assert.equal(estimatedWalkingMinutes(NaN), null);
});

test("departure time defaults use local hours and zero-padded minutes", () => {
  assert.equal(currentLocalTime(new Date(2026, 8, 22, 0, 5)), "00:05");
  assert.equal(currentLocalTime(new Date(2026, 8, 22, 23, 59)), "23:59");
});

test("only a complete valid departure time can be applied on submit", () => {
  for (const time of ["00:00", "06:00", "22:30", "23:59"]) assert.equal(isValidDepartureTime(time), true);
  for (const time of ["", "22:", "24:00", "12:60", "9:00"]) assert.equal(isValidDepartureTime(time), false);
});

test("direct requests carry departure time alongside safety and stair weights", () => {
  for (const time of ["00:00", "06:00", "20:00", "23:59"]) {
    const payload = buildDirectRouteToolCall(origin, destination, { safety: 70, stairs: 40 }, "user-1", time);
    assert.equal(payload.arguments.departure_time, time);
    assert.equal(payload.arguments.stairs_weight, 0.4);
    assert.equal(payload.arguments.preferences[1].weight, 70);
  }
});

test("cleared or invalid departure times cannot be submitted even with criteria collapsed", () => {
  for (const time of ["", "24:00", "20:60", "9:00"]) {
    assert.throws(() => buildDirectRouteToolCall(origin, destination, { safety: 0, stairs: 0 }, "user-1", time), /출발 시간/);
  }
});

test("direct search maps safety ranking and stairs_weight without slope fields", () => {
  const payload = buildDirectRouteToolCall(origin, destination, { safety: 70, stairs: 40 }, "user-1");
  assert.equal(payload.arguments.stairs_weight, 0.4);
  assert.deepEqual(payload.arguments.preferences, [
    { factor: "distance_m", direction: "minimize", weight: 30 },
    { factor: "safety_score", direction: "maximize", weight: 70 },
  ]);
  assert.equal("slope_weight" in payload.arguments, false);
});

test("map-selected coordinates bypass the text place resolver", async () => {
  let resolverCalls = 0;
  const resolved = await resolveDirectLocation(
    {
      displayName: "인하대학교 본관",
      source: "map",
      latitude: 37.45,
      longitude: 126.65,
    },
    async () => {
      resolverCalls += 1;
      return origin;
    },
  );

  assert.equal(resolverCalls, 0);
  assert.equal(resolved.source, "map");
  assert.equal(resolved.latitude, 37.45);
});

test("intersection slider maps to bounded API weight and proximity ranking, not slope", () => {
  for (const [slider, expected] of [[0, 0], [50, 0.5], [100, 1], [150, 1], [-10, 0]]) {
    const payload = buildDirectRouteToolCall(origin, destination, { safety: 70, stairs: 40, intersection: slider }, "user-1");
    assert.equal(payload.arguments.intersection_weight, expected);
    assert.equal(payload.arguments.stairs_weight, 0.4);
    assert.equal("slope_weight" in payload.arguments, false);
    const preference = payload.arguments.preferences.find((p) => p.factor === "intersection_distance_m");
    assert.equal(preference?.weight ?? 0, expected * 100);
  }
});

test("editing a text location uses the place resolver", async () => {
  let requestedName = "";
  await resolveDirectLocation(
    { displayName: "주안역", source: "text" },
    async (name) => {
      requestedName = name;
      return origin;
    },
  );
  assert.equal(requestedName, "주안역");
});

test("a shortest recommendation is compared with the safe route", () => {
  const displayed = selectDisplayedCandidates(
    [candidate("shortest"), candidate("balanced"), candidate("safe")],
    "shortest",
  );
  assert.deepEqual(displayed.map((item) => item.label), ["추천 경로", "안전 경로"]);
  assert.deepEqual(displayed.map((item) => item.candidate.route_type), ["shortest", "safe"]);
});

test("a non-shortest recommendation is compared with the shortest route", () => {
  const displayed = selectDisplayedCandidates(
    [candidate("shortest"), candidate("balanced"), candidate("safe")],
    "safe",
  );
  assert.deepEqual(displayed.map((item) => item.label), ["추천 경로", "최단 경로"]);
  assert.deepEqual(displayed.map((item) => item.candidate.route_type), ["safe", "shortest"]);
});

test("identical segment sequences are displayed only once", () => {
  const shortest = candidate("shortest");
  const safe = candidate("safe");
  safe.route.properties.road_segments = shortest.route.properties.road_segments;

  const displayed = selectDisplayedCandidates([shortest, candidate("balanced"), safe], "shortest");

  assert.deepEqual(displayed.map((item) => item.label), ["추천 경로"]);
});

test("a safe alternative is used when recommendation and shortest are the same route", () => {
  const shortest = candidate("shortest");
  const balanced = candidate("balanced");
  balanced.route.properties.road_segments = shortest.route.properties.road_segments;

  const displayed = selectDisplayedCandidates(
    [shortest, balanced, candidate("safe")],
    "balanced",
  );

  assert.deepEqual(displayed.map((item) => item.label), ["추천 경로", "안전 경로"]);
  assert.deepEqual(displayed.map((item) => item.candidate.route_type), ["balanced", "safe"]);
});

test("geometry is the fallback identity when segment metadata is absent", () => {
  const shortest = candidate("shortest");
  const safe = candidate("safe");
  delete shortest.route.properties.road_segments;
  delete safe.route.properties.road_segments;
  safe.route.geometry.coordinates = shortest.route.geometry.coordinates;

  assert.equal(selectDisplayedCandidates([shortest, safe], "shortest").length, 1);
});
