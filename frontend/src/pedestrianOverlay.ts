import type { RoadViewport } from "./roadViewport";

// Display every collected OSM highway way, including vehicle-only roads.
// This inspection layer is separate from the pedestrian routing network.

export const PEDESTRIAN_OVERLAY_COLOR = "#12b886";
export const PEDESTRIAN_OVERLAY_WIDTH = 2;

// Unlike detailed safety analysis, this lightweight overlay remains visible
// across district-scale pans/zoom-outs. Still avoid fetching a whole country.
export function pedestrianRequestBounds(view: RoadViewport): RoadViewport | null {
  const width = view.east - view.west;
  const height = view.north - view.south;
  if (!Object.values(view).every(Number.isFinite)
    || width <= 0 || height <= 0 || width > 0.18 || height > 0.14
    || view.west < -180 || view.east > 180 || view.south < -90 || view.north > 90) return null;
  return {
    west: Math.max(-180, view.west - width * 0.2),
    south: Math.max(-90, view.south - height * 0.2),
    east: Math.min(180, view.east + width * 0.2),
    north: Math.min(90, view.north + height * 0.2),
  };
}

export function isPedestrianOverlayFeature(feature: {
  properties: Record<string, unknown>;
  geometry: { type: string; coordinates: number[][] };
}): boolean {
  return feature.geometry.type === "LineString"
    && feature.geometry.coordinates.length >= 2
    && feature.geometry.coordinates.every(([lon, lat]) =>
      Number.isFinite(lon) && Number.isFinite(lat)
      && Math.abs(lon) <= 180 && Math.abs(lat) <= 90);
}
