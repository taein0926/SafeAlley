import assert from "node:assert/strict";
import test from "node:test";
import { recommendationBadges } from "./recommendationBadges.ts";

test("all four badges stay visible even when no recommendation condition is applied", () => {
  assert.deepEqual(recommendationBadges([]), [
    { factor: "distance", applied: false }, { factor: "safety", applied: false },
    { factor: "stairs", applied: false }, { factor: "crossing", applied: false },
  ]);
});

test("only conditions explicitly returned by the API are marked applied", () => {
  assert.deepEqual(recommendationBadges(["safety", "stairs"]), [
    { factor: "distance", applied: false }, { factor: "safety", applied: true },
    { factor: "stairs", applied: true }, { factor: "crossing", applied: false },
  ]);
  assert.deepEqual(recommendationBadges(["distance"]), [
    { factor: "distance", applied: true }, { factor: "safety", applied: false },
    { factor: "stairs", applied: false }, { factor: "crossing", applied: false },
  ]);
});

test("all conditions can apply and are stable and deduplicated", () => {
  assert.deepEqual(recommendationBadges(["crossing", "safety", "distance", "safety", "stairs"]), [
    { factor: "distance", applied: true }, { factor: "safety", applied: true },
    { factor: "stairs", applied: true }, { factor: "crossing", applied: true },
  ]);
});
