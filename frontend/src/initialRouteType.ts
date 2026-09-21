import type { RouteCandidate, RouteType } from "./types";

export function initialRouteType(
  candidates: readonly Pick<RouteCandidate, "route_type">[],
): RouteType | null {
  return candidates.find((candidate) => candidate.route_type === "balanced")?.route_type
    ?? candidates[0]?.route_type
    ?? null;
}
