import type { AgentExecutionResponse } from "./types";

export type RecommendationFactor = NonNullable<AgentExecutionResponse["recommendation_factors"]>[number];

// The API reports evaluated recommendation conditions, not guaranteed outcomes.
// Keep all four badges visible without inventing an applied preference.
export function recommendationBadges(factors: readonly RecommendationFactor[]) {
  const applied = new Set(factors);
  const order: RecommendationFactor[] = ["distance", "safety", "stairs", "crossing"];
  return order.map((factor) => ({ factor, applied: applied.has(factor) }));
}
