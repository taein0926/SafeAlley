export const CONDITION_ORDER = ["distance", "streetlight", "cctv", "safety", "stairs", "crossing", "time"] as const;
export type CardFactor = typeof CONDITION_ORDER[number];
export type CardState = "analyzing" | "applied" | "not_applied";
export type ConditionCard = {
  factor: CardFactor; state: CardState;
  direction?: "maximize" | "minimize" | "avoid" | null;
  period?: "day" | "night" | null;
  confidence?: number | null;
  judgment?: "apply" | "skip" | "pending" | "avoid" | "minimize" | "day" | "night" | null;
};
export const CONDITION_LABELS: Record<CardFactor, string> = {
  distance: "최단 거리", safety: "안전시설", streetlight: "가로등 우선", cctv: "CCTV 우선",
  stairs: "계단 회피", crossing: "건널목 회피", time: "시간대 고려",
};
export const CARD_STATE_LABELS: Record<CardState, string> = { analyzing: "분석 중", applied: "적용", not_applied: "미적용" };

export function emptyConditionCards(state: CardState = "analyzing"): ConditionCard[] {
  return CONDITION_ORDER.map((factor) => ({ factor, state }));
}

export function conditionCards(legacy: readonly string[], conditions?: readonly ConditionCard[]): ConditionCard[] {
  const byFactor = new Map(conditions?.map((card) => [card.factor, card]) ?? []);
  const applied = new Set(legacy);
  return CONDITION_ORDER.map((factor) => byFactor.get(factor) ?? {
    factor, state: applied.has(factor) ? "applied" : "not_applied",
  });
}
