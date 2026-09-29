// Shared by the map points and the direct-search map selection buttons.
export const ROUTE_MARKER_COLORS = { origin: "#4fe0ae", destination: "#ff6b7d" } as const;

export function routeMarkerImage(kind: keyof typeof ROUTE_MARKER_COLORS): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="${ROUTE_MARKER_COLORS[kind]}" stroke="white" stroke-width="3"/></svg>`,
  )}`;
}
