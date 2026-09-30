type FacilityToggle = "streetlights" | "cctvs" | "helpPoints" | "stairsAndBridges";

// A single visual family for controls; map markers keep their own category colors.
const pictograms: Record<FacilityToggle, string> = {
  streetlights: '<path d="M17 28c0-4-5-6-5-12a10 10 0 0 1 20 0c0 6-5 8-5 12M17 28h10M18 32h8M20 36h4"/>',
  cctvs: '<g transform="rotate(-25 22 22)"><path d="M10 13h23v12H10zM6 16h4v6H6M8 10h27M22 26v7h11v-7"/></g>',
  helpPoints: '<path d="M22 8l12 5v9c0 6-6 11-12 14-6-3-12-8-12-14v-9z"/><path d="m22 14 2.3 4.7 5.2.8-3.8 3.7.9 5.2-4.6-2.5-4.6 2.5.9-5.2-3.8-3.7 5.2-.8z" fill="#34495e" stroke="none"/>',
  stairsAndBridges: '<path d="M9 34v-7h7v-7h7v-7h7V8h5v26Z" fill="#34495e" stroke="none"/><path d="M9 19 19 9M11 9h8v8"/>',
};

const images = Object.fromEntries(Object.entries(pictograms).map(([kind, pictogram]) => [kind,
  `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 44 44"><g transform="translate(3.3 3.3) scale(0.85)" fill="none" stroke="#34495e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${pictogram}</g></svg>`)}`,
])) as Record<FacilityToggle, string>;

export function facilityToggleImage(kind: FacilityToggle): string { return images[kind]; }
