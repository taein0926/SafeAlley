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
