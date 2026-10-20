import assert from "node:assert/strict";
import test from "node:test";
import { CONDITION_ORDER, conditionCards, type ConditionCard } from "./conditionCards.ts";

test("all eight current condition cards stay visible without invented requests", () => {
  assert.deepEqual(conditionCards([]), CONDITION_ORDER.map(factor => ({ factor, state: "not_applied" })));
});

test("structured API decisions override legacy safety flags without inferring facilities", () => {
  const conditions: ConditionCard[] = [
    { factor: "streetlight", state: "not_applied", reason: "낮에는 가로등을 제외합니다" },
    { factor: "cctv", state: "applied" },
    { factor: "safety", state: "not_applied" },
  ];
  const cards = conditionCards(["safety", "stairs"], conditions);
  assert.equal(cards.length, 8);
  assert.deepEqual(cards.filter(card => card.state === "applied").map(card => card.factor), ["cctv"]);
  assert.equal(cards.find(card => card.factor === "streetlight")?.reason, conditions[0].reason);
});

test("legacy factors remain deduplicated compatibility input to the current eight-card UI", () => {
  const cards = conditionCards(["crossing", "safety", "distance", "safety", "stairs"]);
  assert.deepEqual(cards.map(card => card.factor), [...CONDITION_ORDER]);
  assert.deepEqual(cards.filter(card => card.state === "applied").map(card => card.factor),
    ["distance", "safety", "stairs", "crossing"]);
});
