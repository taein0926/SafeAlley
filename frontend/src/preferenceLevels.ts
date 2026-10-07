// Keep the API's existing 0–100 weights; expose just three UI choices.
export const PREFERENCE_LEVELS = [
  { value: 0, label: "낮음" },
  { value: 50, label: "중간" },
  { value: 100, label: "높음" },
] as const;

export function snapPreferenceWeight(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round(Math.min(100, Math.max(0, value)) / 50) * 50;
}

export function preferenceLevelLabel(value: number, labels?: readonly [string, string, string]): string {
  const index = snapPreferenceWeight(value) / 50;
  return labels?.[index] ?? PREFERENCE_LEVELS[index].label;
}
