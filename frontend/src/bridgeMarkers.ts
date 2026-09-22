function icon(background: string, border: string): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect x="1" y="1" width="42" height="42" rx="11" fill="${background}" stroke="${border}" stroke-width="2"/><path d="M7 30l7-10h16l7 10M14 20V12m16 8V12M14 14h16M18 14v6m8-6v6M14 20v13m16-13v13" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  )}`;
}

export const CONNECTED_BRIDGE_IMAGE = icon("#126779", "#a5f1ff");
export const REFERENCE_BRIDGE_IMAGE = icon("#77501c", "#ffd388");

export function bridgeMarkerPosition(coordinates: number[]): [number, number] | null {
  const [x, y] = coordinates;
  return Number.isFinite(x) && Number.isFinite(y) && x >= -180 && x <= 180 && y >= -90 && y <= 90
    ? [x, y] : null;
}
