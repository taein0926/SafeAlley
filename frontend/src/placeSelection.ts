import type { ResolvedPlace, RouteQueryResponse } from "./types";

export type MapFocusBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export type PlaceSelectionTarget = "origin" | "destination";
export type SelectedPlaces = Partial<Record<PlaceSelectionTarget, ResolvedPlace>>;

export type MapPlaceCandidate = { label: string; place: ResolvedPlace };

// Display-only labels: do not rename DB places or change their routing coordinates.
export function silverTownMapCandidates(error: PlaceCandidatesRequiredError | null): MapPlaceCandidate[] {
  if (!error || error.target !== "destination"
    || error.placeName?.replace(/\s/g, "") !== "실버타운") return [];
  return error.candidates.map((place, index) => ({ label: String.fromCharCode(65 + index), place }));
}

export function candidateFocusBounds(place: ResolvedPlace): MapFocusBounds {
  // Show the surrounding streets, not only the candidate building.
  // Previewing must not change the selected route endpoints.
  return {
    west: place.longitude - 0.0012,
    south: place.latitude - 0.0009,
    east: place.longitude + 0.0012,
    north: place.latitude + 0.0009,
  };
}

export class PlaceCandidatesRequiredError extends Error {
  readonly candidates: readonly ResolvedPlace[];
  readonly target?: PlaceSelectionTarget;
  readonly placeName?: string;

  constructor(
    message: string,
    candidates: readonly ResolvedPlace[],
    target?: PlaceSelectionTarget,
    placeName?: string,
  ) {
    super(message);
    this.name = "PlaceCandidatesRequiredError";
    this.candidates = candidates;
    this.target = target;
    this.placeName = placeName;
  }

  forTarget(target: PlaceSelectionTarget): PlaceCandidatesRequiredError {
    return new PlaceCandidatesRequiredError(this.message, this.candidates, target, this.placeName);
  }
}
export async function resolveSelectedPlaces(
  interpretation: RouteQueryResponse["interpretation"],
  selected: SelectedPlaces,
  resolver: (name: string) => Promise<ResolvedPlace>,
): Promise<{ origin: ResolvedPlace; destination: ResolvedPlace }> {
  const resolved = { ...selected };
  for (const target of ["origin", "destination"] as const) {
    if (resolved[target]) continue;
    const name = interpretation[`${target}_name`];
    if (!name) throw new Error("질문에 출발지와 도착지를 모두 입력해 주세요.");
    try {
      resolved[target] = await resolver(name);
    } catch (error) {
      if (error instanceof PlaceCandidatesRequiredError || error instanceof PlaceSelectionRequiredError) {
        throw error.forTarget(target);
      }
      throw error;
    }
  }
  return resolved as { origin: ResolvedPlace; destination: ResolvedPlace };
}

export class PlaceSelectionRequiredError extends Error {
  readonly focus: MapFocusBounds;
  readonly target?: PlaceSelectionTarget;
  readonly placeName?: string;

  constructor(
    message: string,
    focus: MapFocusBounds,
    target?: PlaceSelectionTarget,
    placeName?: string,
  ) {
    super(message);
    this.name = "PlaceSelectionRequiredError";
    this.focus = focus;
    this.target = target;
    this.placeName = placeName;
  }

  forTarget(target: PlaceSelectionTarget): PlaceSelectionRequiredError {
    return new PlaceSelectionRequiredError(this.message, this.focus, target, this.placeName);
  }
}

function validBounds(value: unknown): value is MapFocusBounds {
  if (!value || typeof value !== "object") return false;
  const bounds = value as Record<string, unknown>;
  return ["west", "south", "east", "north"].every((key) =>
    typeof bounds[key] === "number" && Number.isFinite(bounds[key]))
    && Number(bounds.west) < Number(bounds.east)
    && Number(bounds.south) < Number(bounds.north);
}

export function errorFromApiDetail(detail: unknown, fallback: string): Error {
  if (typeof detail === "string") return new Error(detail);
  if (!detail || typeof detail !== "object") return new Error(fallback);
  const value = detail as Record<string, unknown>;
  const message = typeof value.message === "string" ? value.message : fallback;
  const target = value.target === "origin" || value.target === "destination"
    ? value.target : undefined;
  const placeName = typeof value.place_name === "string" ? value.place_name : undefined;
  if (value.code === "place_selection_required" && Array.isArray(value.candidates)) {
    const candidates = value.candidates.filter((item): item is ResolvedPlace => {
      if (!item || typeof item !== "object") return false;
      const place = item as Record<string, unknown>;
      return typeof place.name === "string" && place.name.trim().length > 0
        && typeof place.source === "string"
        && typeof place.latitude === "number" && Number.isFinite(place.latitude) && Math.abs(place.latitude) <= 90
        && typeof place.longitude === "number" && Number.isFinite(place.longitude) && Math.abs(place.longitude) <= 180
        && (place.address === null || typeof place.address === "string")
        && (place.category === null || typeof place.category === "string");
    });
    if (candidates.length > 1) return new PlaceCandidatesRequiredError(message, candidates, target, placeName);
    return new Error(message);
  }
  if (value.code !== "building_selection_required" || !validBounds(value.focus)) {
    return new Error(message);
  }
  return new PlaceSelectionRequiredError(
    message,
    value.focus,
    target,
    placeName,
  );
}
