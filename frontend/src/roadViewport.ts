export type RoadViewport = {
  west: number;
  south: number;
  east: number;
  north: number;
};

// Detailed safety segments are useful at neighborhood scale, not at city scale.
const MAX_VIEW_WIDTH = 0.018;
const MAX_VIEW_HEIGHT = 0.014;
const PADDING_RATIO = 0.35;

export function roadRequestBounds(view: RoadViewport): RoadViewport | null {
  const width = view.east - view.west;
  const height = view.north - view.south;
  if (
    ![view.west, view.south, view.east, view.north].every(Number.isFinite) ||
    width <= 0 ||
    height <= 0 ||
    width > MAX_VIEW_WIDTH ||
    height > MAX_VIEW_HEIGHT
  ) return null;

  return {
    west: view.west - width * PADDING_RATIO,
    south: view.south - height * PADDING_RATIO,
    east: view.east + width * PADDING_RATIO,
    north: view.north + height * PADDING_RATIO,
  };
}

export function viewportIsInside(view: RoadViewport, loaded: RoadViewport): boolean {
  return (
    view.west >= loaded.west &&
    view.south >= loaded.south &&
    view.east <= loaded.east &&
    view.north <= loaded.north
  );
}

export function roadBboxQuery(bounds: RoadViewport): string {
  return [bounds.west, bounds.south, bounds.east, bounds.north]
    .map((value) => value.toFixed(6))
    .join(",");
}

// Frame the existing building layer without downloading every road just for its extent.
export function geometryBounds(coordinates: unknown[]): RoadViewport | null {
  let bounds: RoadViewport | null = null;
  function visit(value: unknown): void {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") {
      const [longitude, latitude] = value;
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;
      if (!bounds) bounds = { west: longitude, east: longitude, south: latitude, north: latitude };
      else {
        bounds.west = Math.min(bounds.west, longitude);
        bounds.east = Math.max(bounds.east, longitude);
        bounds.south = Math.min(bounds.south, latitude);
        bounds.north = Math.max(bounds.north, latitude);
      }
      return;
    }
    for (const child of value) visit(child);
  }
  visit(coordinates);
  return bounds;
}
