// One shared view for initial loading and the station-centred location button.
export const JUAN_INITIAL_VIEW = { longitude: 126.6804, latitude: 37.4649, height: 1400 } as const;

export function zoomTargetHeight(height: number, direction: "in" | "out"): number {
  const current = Number.isFinite(height) && height > 0 ? height : JUAN_INITIAL_VIEW.height;
  return Math.min(2_000_000, Math.max(30, current * (direction === "in" ? 0.5 : 2)));
}
