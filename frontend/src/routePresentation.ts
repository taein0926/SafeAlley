import type { RouteCandidate, RouteType } from "./types";

export const ACTIVE_ROUTE_COLOR = "#007aff";
export const ALTERNATIVE_ROUTE_COLOR = "#89919d";

// Shared segments select the topmost active route, not an arbitrary hidden line.
export function routePickPriority(routeType: RouteType | undefined, selectedType: RouteType | null): number {
  return routeType !== undefined && routeType === selectedType ? 6 : 5;
}

export function routeLineStyle(routeType: RouteType, selectedType: RouteType | null, _night = false) {
  const selected = routeType === selectedType;
  return {
    color: selected ? ACTIVE_ROUTE_COLOR : ALTERNATIVE_ROUTE_COLOR,
    width: selected ? 9 : 6,
    casingWidth: selected ? 12 : 8,
    casingColor: selected ? "#0054bb" : "#707987",
    zIndex: selected ? 4 : 2,
  };
}

// Half-discs extend only beyond the line end: a full outlined circle would
// paint a visible seam across the line. SVG keeps the cap crisp at any DPI.
export function routeCapPath(width: number): string {
  const r = width / 2;
  return `M 0 ${-r} A ${r} ${r} 0 0 1 0 ${r} Z`;
}

export function routeEndCaps(candidates: RouteCandidate[], selected: RouteType | null) {
  return [...candidates].sort((a, b) => Number(a.route_type === selected) - Number(b.route_type === selected))
    .flatMap(candidate => {
      const coordinates = candidate.route.geometry.coordinates;
      if (coordinates.length < 2) return [];
      return [0, coordinates.length - 1].flatMap(index => {
        const position = coordinates[index];
        const ordered = index === 0 ? coordinates : [...coordinates].reverse();
        const neighbor = ordered.find(p => p[0] !== position[0] || p[1] !== position[1]);
        return neighbor ? [{ routeType: candidate.route_type, position, neighbor }] : [];
      });
    });
}

// Stable across selection changes, but changes even for equal-sized new geometries.
export function routeGeometrySignature(candidates: RouteCandidate[]): string {
  return JSON.stringify(candidates.map(({ route_type, route }) => [route_type, route.geometry.coordinates]));
}
