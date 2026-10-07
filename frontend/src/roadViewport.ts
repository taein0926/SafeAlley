export type RoadViewport = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export function roadBboxQuery(bounds: RoadViewport): string {
  return [bounds.west, bounds.south, bounds.east, bounds.north]
    .map((value) => value.toFixed(6))
    .join(",");
}
