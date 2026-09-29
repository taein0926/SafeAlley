function icon(pictogram: string, border: string): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect x="1" y="1" width="42" height="42" rx="9" fill="#ffffff" stroke="${border}" stroke-width="2"/><g fill="none" stroke="${pictogram}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 33h5v-6h5v-6h14v6h5v6h5"/><path d="M15 21V12h14v9M22 12v9M17 22v12m10-12v12"/></g></svg>`,
  )}`;
}

export const CONNECTED_BRIDGE_IMAGE = icon("#2463a5", "#2463a5");
export const REFERENCE_BRIDGE_IMAGE = icon("#95631d", "#95631d");

export function bridgeMarkerPosition(coordinates: number[]): [number, number] | null {
  const [x, y] = coordinates;
  return Number.isFinite(x) && Number.isFinite(y) && x >= -180 && x <= 180 && y >= -90 && y <= 90
    ? [x, y] : null;
}
