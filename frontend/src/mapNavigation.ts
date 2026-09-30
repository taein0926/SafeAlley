// One shared view for initial loading and the location button.
export const INITIAL_MAP_VIEW = { longitude: 126.66204388583374, latitude: 37.46883423059321, height: 1000 } as const;

export function zoomTargetHeight(height: number, direction: "in" | "out"): number {
  const current = Number.isFinite(height) && height > 0 ? height : INITIAL_MAP_VIEW.height;
  return Math.min(2_000_000, Math.max(30, current * (direction === "in" ? 0.5 : 2)));
}
