export type MapFocusBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export type PlaceSelectionTarget = "origin" | "destination";

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
  if (value.code !== "building_selection_required" || !validBounds(value.focus)) {
    return new Error(message);
  }
  const target = value.target === "origin" || value.target === "destination"
    ? value.target : undefined;
  return new PlaceSelectionRequiredError(
    message,
    value.focus,
    target,
    typeof value.place_name === "string" ? value.place_name : undefined,
  );
}
