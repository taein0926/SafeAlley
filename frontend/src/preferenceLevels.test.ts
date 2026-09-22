import assert from "node:assert/strict";
import test from "node:test";
import { PREFERENCE_LEVELS, preferenceLevelLabel, snapPreferenceWeight } from "./preferenceLevels.ts";
import { buildDirectRouteToolCall } from "./routeSearch.ts";
import type { ResolvedPlace } from "./types.ts";

test("three preference steps use descriptive labels, not displayed scores", () => {
  assert.deepEqual(PREFERENCE_LEVELS.map((level) => level.label), ["낮음", "중간", "높음"]);
  for (const level of PREFERENCE_LEVELS) {
    assert.equal(snapPreferenceWeight(level.value), level.value);
    assert.equal(preferenceLevelLabel(level.value), level.label);
  }
  for (let value = -10; value <= 110; value++) {
    assert.ok([0, 50, 100].includes(snapPreferenceWeight(value)));
  }
  assert.equal(snapPreferenceWeight(NaN), 0);
});

test("low/medium/high preserve existing route API weights", () => {
  const place: ResolvedPlace = { name: "주안역", latitude: 37.4649, longitude: 126.6804,
    category: null, address: null, source: "test" };
  for (const { value } of PREFERENCE_LEVELS) {
    const { arguments: args } = buildDirectRouteToolCall(place, place,
      { safety: value, stairs: value, intersection: value }, "test", "22:00");
    assert.equal(args.stairs_weight, value / 100);
    assert.equal(args.intersection_weight, value / 100);
    assert.equal(args.preferences.find((p) => p.factor === "safety_score")?.weight ?? 0, value);
    assert.equal(args.preferences.find((p) => p.factor === "distance_m")?.weight ?? 0, 100 - value);
    assert.equal(args.departure_time, "22:00");
  }
});
