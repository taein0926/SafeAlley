import type { CardFactor } from "./conditionCards";
type FacilityToggle = "streetlights" | "cctvs" | "helpPoints" | "stairsAndBridges";

// Controls share condition glyphs; map markers and category data are unchanged.
const factors: Record<FacilityToggle, CardFactor> = {
  streetlights: "streetlight", cctvs: "cctv", helpPoints: "safety", stairsAndBridges: "stairs",
};

export function facilityToggleFactor(kind: FacilityToggle): CardFactor { return factors[kind]; }
