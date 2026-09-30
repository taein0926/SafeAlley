import type { RouteCandidate, RouteType } from "./types";

type XY = readonly [number, number];
export type RouteGuidePoint = { longitude: number; latitude: number; kind: "crossing" };

const valid = (p: number[]): boolean => p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])
  && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;
const distance = (a: XY, b: XY): number => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function selectedRouteGuidePoints(candidates: RouteCandidate[], selected: RouteType | null): RouteGuidePoint[] {
  const route = candidates.find(c => c.route_type === selected)?.route;
  const coordinates = route?.geometry.coordinates ?? [];
  if (!route || coordinates.length < 2 || !coordinates.every(valid)) return [];
  const origin = coordinates[0];
  const longitudeScale = 111_320 * Math.cos(origin[1] * Math.PI / 180);
  const project = (p: number[]): XY => [(p[0] - origin[0]) * longitudeScale, (p[1] - origin[1]) * 111_320];
  const points = coordinates.map(project);
  const markers: RouteGuidePoint[] = [];
  const add = (p: number[], kind: RouteGuidePoint["kind"]) => {
    if (!valid(p)) return;
    const xy = project(p);
    // Keep distinct crossing ends even when the crossing is very short.
    // Only identical coordinates (e.g. a shared landing) are duplicates.
    if (distance(xy, points[0]) < 5 || distance(xy, points[points.length - 1]) < 5
      || markers.some(marker => marker.longitude === p[0] && marker.latitude === p[1])) return;
    markers.push({ longitude: p[0], latitude: p[1], kind });
  };

  // Only explicit OSM crossing groups qualify. Joining split pieces avoids a
  // dot at every intermediate OSM node, while retaining both crossing ends.
  let crossing: { group: number; first: number[]; last: number[] } | null = null;
  const flush = () => {
    if (crossing) { add(crossing.first, "crossing"); add(crossing.last, "crossing"); }
    crossing = null;
  };
  for (const segment of route.properties.road_segments ?? []) {
    const c = segment.coordinates;
    const group = segment.crossing_group;
    if (typeof group !== "number" || !Number.isFinite(group) || c.length < 2 || !c.every(valid)) {
      flush(); continue;
    }
    if (crossing && crossing.group === group && distance(project(crossing.last), project(c[0])) < 1) {
      crossing.last = c[c.length - 1];
    } else {
      flush(); crossing = { group, first: c[0], last: c[c.length - 1] };
    }
  }
  flush();
  return markers;
}
