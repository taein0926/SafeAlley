import type { RouteCandidate, RouteType } from "./types";

export const ACTIVE_ROUTE_COLOR = "#1261ff";
export const ALTERNATIVE_ROUTE_COLOR = "#8b96a7";

// Shared segments select the topmost active route, not an arbitrary hidden line.
export function routePickPriority(routeType: RouteType | undefined, selectedType: RouteType | null): number {
  return routeType !== undefined && routeType === selectedType ? 6 : 5;
}

export function routeLineStyle(routeType: RouteType, selectedType: RouteType | null, night = false) {
  const selected = routeType === selectedType;
  return {
    color: selected ? ACTIVE_ROUTE_COLOR : ALTERNATIVE_ROUTE_COLOR,
    width: selected ? 9 : 6,
    casingWidth: selected ? 15 : 10.5,
    casingColor: night ? "#ffffff" : "#16365c",
    zIndex: selected ? 4 : 2,
  };
}

// Stable across selection changes, but changes even for equal-sized new geometries.
export function routeGeometrySignature(candidates: RouteCandidate[]): string {
  return JSON.stringify(candidates.map(({ route_type, route }) => [route_type, route.geometry.coordinates]));
}
