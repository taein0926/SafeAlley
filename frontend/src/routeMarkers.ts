import type { RouteCandidate, RouteType } from "./types";

// Shared compact silhouette, rendered as vector artwork outside the WebGL canvas.
export const ROUTE_MARKER_COLORS = { origin: "#03c75a", destination: "#f4433e" } as const;
export type RouteMarkerLocation = { kind: keyof typeof ROUTE_MARKER_COLORS; longitude: number; latitude: number };
const PIN_CONTOUR = "M20 3.5C11.8 3.5 5.5 9.8 5.5 18c0 7.5 8.5 19.4 14.5 27.5C26 37.4 34.5 25.5 34.5 18c0-8.2-6.3-14.5-14.5-14.5Z";

// Search controls are outline-only; map pins retain their filled, labelled style.
export function routeInputMarkerImage(kind: keyof typeof ROUTE_MARKER_COLORS): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200" viewBox="0 0 40 50"><path d="${PIN_CONTOUR}" fill="none" stroke="${ROUTE_MARKER_COLORS[kind]}" stroke-width="2.2" stroke-linejoin="round"/></svg>`,
  )}`;
}

// Anchor the selected route sign halfway along its actual polyline, not its bbox.
export function selectedRouteLabelLocation(candidates: RouteCandidate[], selectedType: RouteType | null): { longitude: number; latitude: number } | null {
  const c = candidates.find(candidate => candidate.route_type === selectedType)?.route.geometry.coordinates ?? [];
  if (c.length < 2 || c.some(p => !Number.isFinite(p[0]) || !Number.isFinite(p[1]) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90)) return null;
  const scale = Math.cos(c[0][1] * Math.PI / 180);
  const lengths = c.slice(1).map((p, i) => Math.hypot((p[0] - c[i][0]) * scale, p[1] - c[i][1]));
  let remaining = lengths.reduce((sum, length) => sum + length, 0) / 2;
  if (!remaining) return null;
  for (let i = 0; i < lengths.length; i++) {
    if (lengths[i] <= 0) continue;
    if (remaining <= lengths[i]) {
      const fraction = remaining / lengths[i];
      return { longitude: c[i][0] + (c[i + 1][0] - c[i][0]) * fraction,
        latitude: c[i][1] + (c[i + 1][1] - c[i][1]) * fraction };
    }
    remaining -= lengths[i];
  }
  return null;
}

export function routeMarkerImage(kind: keyof typeof ROUTE_MARKER_COLORS): string {
  const start = kind === "origin";
  const contour = PIN_CONTOUR;
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200" viewBox="0 0 40 50">
      <path d="${contour}" fill="${ROUTE_MARKER_COLORS[kind]}" stroke="${start ? "#00a64c" : "#d73835"}" stroke-width="1"/>
      <text x="20" y="22" text-anchor="middle" fill="white" font-family="Malgun Gothic,Apple SD Gothic Neo,sans-serif" font-size="12" font-weight="700" letter-spacing="-.6">${start ? "출발" : "도착"}</text>
    </svg>`,
  )}`;
}

function validMarker(point: RouteMarkerLocation): boolean {
  return Number.isFinite(point.longitude) && Number.isFinite(point.latitude)
    && Math.abs(point.longitude) <= 180 && Math.abs(point.latitude) <= 90;
}

export function routeMarkerLocations(candidates: RouteCandidate[], selectedType: RouteType | null, drafts: RouteMarkerLocation[]): RouteMarkerLocation[] {
  const selected = candidates.find(candidate => candidate.route_type === selectedType) ?? candidates[0];
  const coordinates = selected?.route.geometry.coordinates ?? [];
  const endpoints: RouteMarkerLocation[] = coordinates.length > 0 ? [
    { kind: "origin", longitude: coordinates[0][0], latitude: coordinates[0][1] },
    { kind: "destination", longitude: coordinates[coordinates.length - 1][0], latitude: coordinates[coordinates.length - 1][1] },
  ] : [];
  // Resolved/search coordinates are the destination, not the snapped graph nodes.
  // Only older results without requested coordinates fall back to road endpoints.
  return (["origin", "destination"] as const).flatMap(kind => {
    const point = drafts.find(p => p.kind === kind && validMarker(p))
      ?? endpoints.find(p => p.kind === kind && validMarker(p));
    return point ? [point] : [];
  });
}

export function routeAccessConnectors(candidates: RouteCandidate[], selectedType: RouteType | null, requested: RouteMarkerLocation[]) {
  const selected = candidates.find(candidate => candidate.route_type === selectedType) ?? candidates[0];
  const coordinates = selected?.route.geometry.coordinates ?? [];
  if (coordinates.length < 2) return [];
  return routeMarkerLocations(candidates, selectedType, requested).flatMap(point => {
    const end = point.kind === "origin" ? coordinates[0] : coordinates[coordinates.length - 1];
    if (!validMarker({ kind: point.kind, longitude: end[0], latitude: end[1] })) return [];
    const meters = Math.hypot((end[0] - point.longitude) * Math.cos(point.latitude * Math.PI / 180), end[1] - point.latitude) * 111_320;
    if (meters < 0.5) return [];
    // Display-only link: not a surveyed entrance/path, never added to route metrics.
    return [{ kind: point.kind, from: [point.longitude, point.latitude] as [number, number],
      to: [end[0], end[1]] as [number, number] }];
  });
}
