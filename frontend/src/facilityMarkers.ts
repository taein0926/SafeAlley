// Shared SVG textures keep dense point layers independent of emoji fonts and image requests.
function marker(background: string, border: string, pictogram: string): string {
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect x="1" y="1" width="42" height="42" rx="11" fill="${background}" stroke="${border}" stroke-width="2"/>${pictogram}</svg>`,
  )}`;
}

export const CCTV_MARKER_IMAGE = marker("#125363", "#a5f1ff",
  '<path d="M9 13l23 5-4 10-22-5z" fill="white"/><path d="M30 22l6 1-2 6-6-1M19 27v7h13v-5" fill="none" stroke="white" stroke-width="3" stroke-linejoin="round"/>');

export const POLICE_MARKER_IMAGE = marker("#245bb4", "#d7e8ff",
  '<path d="M22 7l13 5v10c0 7-7 12-13 15-6-3-13-8-13-15V12z" fill="none" stroke="white" stroke-width="2.5"/><path d="M22 13l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z" fill="white"/>');

export const FIRE_STATION_MARKER_IMAGE = marker("#b63038", "#ffe0df",
  // Outline the digits so 119 stays consistent without depending on installed fonts.
  '<g aria-label="119" fill="none" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 17l4-3v17M6 31h8M17 17l4-3v17M17 31h8"/><path d="M37 22h-5a4 4 0 0 1-4-4v0a4 4 0 0 1 4-4h1a4 4 0 0 1 4 4v9a4 4 0 0 1-4 4h-4"/></g>');

export const HOSPITAL_MARKER_IMAGE = marker("#157747", "#d7ffdf",
  '<path d="M17 9h10v8h8v10h-8v8H17v-8H9V17h8z" fill="white"/>');

export const GENERIC_HELP_MARKER_IMAGE = marker("#674092", "#edddff",
  '<path d="M22 8a11 11 0 0 0-11 11c0 8 11 18 11 18s11-10 11-18A11 11 0 0 0 22 8z" fill="white"/><circle cx="22" cy="19" r="4" fill="#674092"/>');

export function helpPointMarkerImage(category: unknown): string {
  if (category === "police") return POLICE_MARKER_IMAGE;
  if (category === "fire_station") return FIRE_STATION_MARKER_IMAGE;
  if (category === "emergency_medical") return HOSPITAL_MARKER_IMAGE;
  return GENERIC_HELP_MARKER_IMAGE;
}
