import type { RouteCandidate, RouteType } from "./types";

type XY = readonly [number, number];
export type RouteGuidePoint = { longitude: number; latitude: number; kind: "crossing" };

// Crisp, self-contained zebra-crossing symbol; no external image requests.
export const CROSSING_GUIDE_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#fff" stroke="#555" stroke-width="1.8"/><path d="M9 11.5h3L10 21H5.5zm4.5 0h2V21h-4zm3 0h2l2.5 9.5h-4.5zm3.5 0h3l3.5 9.5H22z" fill="#383838"/></svg>'
)}`;

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
  const markers: RouteGuidePoint[] = [];
  const add = (p: number[], kind: RouteGuidePoint["kind"]) => {
    if (!valid(p)) return;
    if (markers.some(marker => marker.longitude === p[0] && marker.latitude === p[1])) return;
    markers.push({ longitude: p[0], latitude: p[1], kind });
  };

  // Join split OSM crossing pieces, then walk half their total length. This
  // keeps the icon on curved crossings instead of averaging their endpoints.
  let crossing: { group: number; coordinates: number[][] } | null = null;
  const flush = () => {
    if (crossing) {
      const c = crossing.coordinates;
      const lengths = c.slice(1).map((p, i) => distance(project(c[i]), project(p)));
      let remaining = lengths.reduce((sum, length) => sum + length, 0) / 2;
      for (let i = 0; i < lengths.length; i++) {
        if (lengths[i] === 0) continue;
        if (remaining <= lengths[i]) {
          const fraction = remaining / lengths[i];
          add([c[i][0] + (c[i + 1][0] - c[i][0]) * fraction,
            c[i][1] + (c[i + 1][1] - c[i][1]) * fraction], "crossing");
          break;
        }
        remaining -= lengths[i];
      }
    }
    crossing = null;
  };
  for (const segment of route.properties.road_segments ?? []) {
    const c = segment.coordinates;
    const group = segment.crossing_group;
    if (typeof group !== "number" || !Number.isFinite(group) || c.length < 2 || !c.every(valid)) {
      flush(); continue;
    }
    if (crossing && crossing.group === group && distance(project(crossing.coordinates[crossing.coordinates.length - 1]), project(c[0])) < 1) {
      crossing.coordinates.push(...c.slice(1));
    } else {
      flush(); crossing = { group, coordinates: c.slice() };
    }
  }
  flush();
  return markers;
}
