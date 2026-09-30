import type { RouteCandidate, RouteType } from "./types";

// Shared compact silhouette, rendered as vector artwork outside the WebGL canvas.
export const ROUTE_MARKER_COLORS = { origin: "#03c75a", destination: "#f4433e" } as const;
export type RouteMarkerLocation = { kind: keyof typeof ROUTE_MARKER_COLORS; longitude: number; latitude: number };

export function routeMarkerImage(kind: keyof typeof ROUTE_MARKER_COLORS): string {
  const start = kind === "origin";
  const contour = "M20 3.5C11.8 3.5 5.5 9.8 5.5 18c0 7.5 8.5 19.4 14.5 27.5C26 37.4 34.5 25.5 34.5 18c0-8.2-6.3-14.5-14.5-14.5Z";
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200" viewBox="0 0 40 50">
      <defs><linearGradient id="pin" x2="0" y2="1"><stop stop-color="${start ? "#06d46a" : "#ff625b"}"/><stop offset="1" stop-color="${ROUTE_MARKER_COLORS[kind]}"/></linearGradient></defs>
      <path d="${contour}" transform="translate(0 1.5)" fill="#182c3e" opacity=".18" stroke="#182c3e" stroke-width="2"/>
      <path d="${contour}" fill="url(#pin)" stroke="${start ? "#00a64c" : "#d73835"}" stroke-width="1"/>
      <path d="M8 16C8.7 9.7 13.7 5.8 20 5.8c6.3 0 11.3 3.9 12 10" fill="none" stroke="white" stroke-opacity=".24" stroke-width="1"/>
      <text x="20" y="22" text-anchor="middle" fill="white" font-family="Malgun Gothic,Apple SD Gothic Neo,sans-serif" font-size="12" font-weight="700" letter-spacing="-.6">${start ? "출발" : "도착"}</text>
    </svg>`,
  )}`;
}

export function routeMarkerLocations(candidates: RouteCandidate[], selectedType: RouteType | null, drafts: RouteMarkerLocation[]): RouteMarkerLocation[] {
  const selected = candidates.find(candidate => candidate.route_type === selectedType) ?? candidates[0];
  const coordinates = selected?.route.geometry.coordinates ?? [];
  const points: RouteMarkerLocation[] = coordinates.length > 0 ? [
    { kind: "origin", longitude: coordinates[0][0], latitude: coordinates[0][1] },
    { kind: "destination", longitude: coordinates[coordinates.length - 1][0], latitude: coordinates[coordinates.length - 1][1] },
  ] : drafts;
  return points.filter(point => Number.isFinite(point.longitude) && Number.isFinite(point.latitude)
    && Math.abs(point.longitude) <= 180 && Math.abs(point.latitude) <= 90);
}
