import { boundsIntersect, geometryBounds, batchTiles, type BuildingBatch, type BuildingTile } from "./buildingViewport.ts";
import type { RoadViewport } from "./roadViewport";

export type FacilityFeature = {
  id: number | string;
  geometry: { type: string; coordinates: unknown };
  properties: Record<string, unknown>;
};
export type FacilityRequest = { batches: BuildingBatch[]; controller: AbortController };

export function facilityBounds(view: RoadViewport | null): RoadViewport | null {
  if (!view || !Object.values(view).every(Number.isFinite)) return null;
  const width = view.east - view.west, height = view.north - view.south;
  if (width <= 0 || height <= 0 || width > 0.18 || height > 0.14 ||
      view.west < -180 || view.east > 180 || view.south < -90 || view.north > 90) return null;
  // At least ~90 m around this city's viewport: larger than the 45 m heat kernel.
  const x = Math.max(0.001, width * 0.2), y = Math.max(0.001, height * 0.2);
  return { west: Math.max(-180, view.west - x), east: Math.min(180, view.east + x),
    south: Math.max(-90, view.south - y), north: Math.min(90, view.north + y) };
}

function tilesFor(bounds: RoadViewport): BuildingTile[] {
  const tiles: BuildingTile[] = [], size = 0.01;
  const edge = (n: number) => Number((n * size).toFixed(6));
  for (let y = Math.floor(bounds.south / size); y < Math.ceil(bounds.north / size - 1e-9); y++) {
    for (let x = Math.floor(bounds.west / size); x < Math.ceil(bounds.east / size - 1e-9); x++) {
      tiles.push({ key: `${x}:${y}`, x, y,
        bounds: { west: edge(x), south: edge(y), east: edge(x + 1), north: edge(y + 1) } });
    }
  }
  return tiles;
}

/** Raw GeoJSON LRU. Only visible records become Cesium objects. No failed/stale tile is cached. */
export class FacilityViewportCache {
  private tiles = new Map<string, { features: FacilityFeature[]; used: number }>();
  private visible: BuildingTile[] = [];
  private pending: FacilityRequest | null = null;
  private clock = 0;
  private limit: number;
  constructor(limit = 96) { this.limit = limit; }

  plan(view: RoadViewport | null): FacilityRequest | null {
    const bounds = facilityBounds(view);
    this.visible = bounds ? tilesFor(bounds) : [];
    for (const tile of this.visible) {
      const cached = this.tiles.get(tile.key);
      if (cached) cached.used = ++this.clock;
    }
    const missing = this.visible.filter((tile) => !this.tiles.has(tile.key));
    const pendingKeys = new Set(this.pending?.batches.flatMap((batch) => batch.tiles.map((tile) => tile.key)));
    if (missing.length && this.pending && missing.every((tile) => pendingKeys.has(tile.key))) return null;
    this.cancel();
    this.evict();
    if (!missing.length) return null;
    return this.pending = { batches: batchTiles(missing), controller: new AbortController() };
  }

  isCurrent(request: FacilityRequest): boolean {
    return this.pending === request && !request.controller.signal.aborted;
  }
  commit(request: FacilityRequest, batch: BuildingBatch, features: FacilityFeature[]): boolean {
    if (!this.isCurrent(request) || !request.batches.includes(batch)) return false;
    const bounded = features.map((feature) => ({ feature, bounds: geometryBounds(feature.geometry.coordinates) }));
    for (const tile of batch.tiles) this.tiles.set(tile.key, {
      features: bounded.filter((item) => item.bounds && boundsIntersect(item.bounds, tile.bounds)).map((item) => item.feature),
      used: ++this.clock,
    });
    if (request.batches.every((b) => b.tiles.every((tile) => this.tiles.has(tile.key)))) this.pending = null;
    this.evict();
    return true;
  }
  features(): FacilityFeature[] {
    const records = new Map<string, FacilityFeature>();
    for (const tile of this.visible) for (const feature of this.tiles.get(tile.key)?.features ?? []) {
      records.set(String(feature.id), feature);
    }
    return [...records.values()];
  }
  get signature(): string { return this.visible.map((tile) => tile.key).sort().join("|"); }
  get loading(): boolean { return this.pending !== null; }
  get cachedTileCount(): number { return this.tiles.size; }
  cancel(): void { this.pending?.controller.abort(); this.pending = null; }
  fail(request: FacilityRequest): void { if (this.isCurrent(request)) this.cancel(); }
  clear(): void { this.cancel(); this.tiles.clear(); this.visible = []; }
  private evict(): void {
    const keep = new Set(this.visible.map((tile) => tile.key));
    for (const [key] of [...this.tiles].sort((a, b) => a[1].used - b[1].used)) {
      if (this.tiles.size <= this.limit) break;
      if (!keep.has(key)) this.tiles.delete(key);
    }
  }
}
