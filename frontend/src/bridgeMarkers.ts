function icon(pictogram: string, border: string): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 44 44"><circle cx="22" cy="22" r="21" fill="#ffffff" stroke="${border}" stroke-width="2"/><g transform="translate(4.4 4.4) scale(0.8)" fill="none" stroke="${pictogram}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 33h5v-6h5v-6h14v6h5v6h5"/><path d="M15 21V12h14v9M22 12v9M17 22v12m10-12v12"/></g></svg>`,
  )}`;
}

export const CONNECTED_BRIDGE_IMAGE = icon("#34495e", "#52677d");
export const REFERENCE_BRIDGE_IMAGE = CONNECTED_BRIDGE_IMAGE;

export function bridgeMarkerPosition(coordinates: number[]): [number, number] | null {
  const [x, y] = coordinates;
  return Number.isFinite(x) && Number.isFinite(y) && x >= -180 && x <= 180 && y >= -90 && y <= 90
    ? [x, y] : null;
}
