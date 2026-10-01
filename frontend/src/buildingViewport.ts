import type { RoadViewport } from "./roadViewport";

export function buildingRequestBounds(view: RoadViewport | null): RoadViewport | null {
  if (!view) return null;
  const width = view.east - view.west;
  const height = view.north - view.south;
  if (
    ![view.west, view.south, view.east, view.north].every(Number.isFinite) ||
    width <= 0 || height <= 0 || width > 0.022 || height > 0.016 ||
    view.west < -180 || view.east > 180 || view.south < -90 || view.north > 90
  ) return null;
  return {
    west: Math.max(-180, view.west - width * 0.2),
    south: Math.max(-90, view.south - height * 0.2),
    east: Math.min(180, view.east + width * 0.2),
    north: Math.min(90, view.north + height * 0.2),
  };
}

const TILE_SIZE = 0.004;
export const MAX_ROUTE_BUILDING_TILES = 16;
export type BuildingTile = { key: string; x: number; y: number; bounds: RoadViewport };
export type BuildingBatch = { tiles: BuildingTile[]; bounds: RoadViewport };
export type BuildingRequest = { batches: BuildingBatch[]; controller: AbortController };
type Decision = { kind: "hidden" | "reuse" | "pending" } | { kind: "load"; request: BuildingRequest };

export function buildingTiles(bounds: RoadViewport): BuildingTile[] {
  const tiles: BuildingTile[] = [];
  for (let y = Math.floor(bounds.south / TILE_SIZE); y < Math.ceil(bounds.north / TILE_SIZE - 1e-9); y++) {
    for (let x = Math.floor(bounds.west / TILE_SIZE); x < Math.ceil(bounds.east / TILE_SIZE - 1e-9); x++) {
      const edge = (n: number) => Number((n * TILE_SIZE).toFixed(6));
      tiles.push({ key: `${x}:${y}`, x, y, bounds: { west: edge(x), south: edge(y), east: edge(x + 1), north: edge(y + 1) } });
    }
  }
  return tiles;
}

// Merge adjacent missing tiles into rectangles. Cached tiles never appear in a request bbox.
export function batchTiles(tiles: BuildingTile[]): BuildingBatch[] {
  const remaining = new Map(tiles.map((tile) => [tile.key, tile]));
  const batches: BuildingBatch[] = [];
  for (const tile of tiles) {
    if (!remaining.has(tile.key)) continue;
    let east = tile.x;
    while (remaining.has(`${east + 1}:${tile.y}`)) east++;
    let north = tile.y;
    while (Array.from({ length: east - tile.x + 1 }, (_, i) => remaining.has(`${tile.x + i}:${north + 1}`)).every(Boolean)) north++;
    const group: BuildingTile[] = [];
    for (let y = tile.y; y <= north; y++) for (let x = tile.x; x <= east; x++) {
      const key = `${x}:${y}`;
      group.push(remaining.get(key)!);
      remaining.delete(key);
    }
    batches.push({ tiles: group, bounds: { ...tile.bounds, east: group[group.length - 1].bounds.east, north: group[group.length - 1].bounds.north } });
  }
  return batches;
}

export function geometryBounds(coordinates: unknown): RoadViewport | null {
  let bounds: RoadViewport | null = null;
  function visit(value: unknown): void {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") {
      const [x, y] = value;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      if (!bounds) bounds = { west: x, east: x, south: y, north: y };
      else {
        bounds.west = Math.min(bounds.west, x); bounds.east = Math.max(bounds.east, x);
        bounds.south = Math.min(bounds.south, y); bounds.north = Math.max(bounds.north, y);
      }
    } else for (const child of value) visit(child);
  }
  visit(coordinates);
  return bounds;
}

export function boundsIntersect(a: RoadViewport, b: RoadViewport): boolean {
  return a.west <= b.east && a.east >= b.west && a.south <= b.north && a.north >= b.south;
}

// Overview: load a bounded corridor instead of every building in the camera bbox.
export function routeBuildingTiles(view: RoadViewport | null, coordinates: number[][]): BuildingTile[] {
  if (!view || ![view.west, view.south, view.east, view.north].every(Number.isFinite) ||
    view.east <= view.west || view.north <= view.south ||
    view.east - view.west > 0.3 || view.north - view.south > 0.3 ||
    view.west < -180 || view.east > 180 || view.south < -90 || view.north > 90 ||
    coordinates.length < 2 || coordinates.some(([x, y]) =>
      !Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90)) return [];
  const core = new Map<string, BuildingTile>();
  const neighbours = new Map<string, BuildingTile>();
  for (let i = 1; i < coordinates.length; i++) {
    const [ax, ay] = coordinates[i - 1];
    const [bx, by] = coordinates[i];
    const steps = Math.min(512, Math.max(1, Math.ceil(Math.max(Math.abs(bx - ax), Math.abs(by - ay)) / (TILE_SIZE / 2))));
    for (let j = 0; j <= steps; j++) {
      const x = ax + (bx - ax) * j / steps;
      const y = ay + (by - ay) * j / steps;
      for (const tile of buildingTiles({ west: x - 0.001, east: x + 0.001, south: y - 0.001, north: y + 0.001 })) {
        if (!boundsIntersect(tile.bounds, view)) continue;
        neighbours.set(tile.key, tile);
        if (tile.x === Math.floor(x / TILE_SIZE) && tile.y === Math.floor(y / TILE_SIZE)) core.set(tile.key, tile);
      }
    }
  }
  const spread = (tiles: BuildingTile[], limit: number): BuildingTile[] => {
    if (limit <= 0) return [];
    if (tiles.length <= limit) return tiles;
    if (limit === 1) return [tiles[Math.floor(tiles.length / 2)]];
    return Array.from({ length: limit }, (_, i) => tiles[Math.round(i * (tiles.length - 1) / (limit - 1))]);
  };
  const selected = spread([...core.values()], MAX_ROUTE_BUILDING_TILES);
  return [...selected, ...spread([...neighbours.values()].filter((tile) => !core.has(tile.key)), MAX_ROUTE_BUILDING_TILES - selected.length)];
}

export class BuildingViewportRequests {
  readonly visible = new Set<string>();
  routeFocused = false;
  private loaded = new Map<string, number>();
  private pending: BuildingRequest | null = null;
  private clock = 0;
  private limit: number;

  constructor(limit = 64) { this.limit = limit; }

  plan(view: RoadViewport | null, route: number[][] = []): Decision {
    const bounds = buildingRequestBounds(view);
    this.routeFocused = !bounds;
    const tiles = bounds ? buildingTiles(bounds) : routeBuildingTiles(view, route);
    this.visible.clear();
    if (!tiles.length) {
      this.cancelPending(); // Keep cached geometry while zoomed out.
      return { kind: "hidden" };
    }
    for (const tile of tiles) {
      this.visible.add(tile.key);
      if (this.loaded.has(tile.key)) this.loaded.set(tile.key, ++this.clock);
    }
    const missing = tiles.filter((tile) => !this.loaded.has(tile.key));
    if (!missing.length) { this.cancelPending(); return { kind: "reuse" }; }
    const pendingKeys = new Set(this.pending?.batches.flatMap((batch) => batch.tiles.map((tile) => tile.key)));
    if (this.pending && missing.every((tile) => pendingKeys.has(tile.key))) return { kind: "pending" };
    this.cancelPending();
    const batches = this.routeFocused ? missing.map((tile) => ({ tiles: [tile], bounds: tile.bounds })) : batchTiles(missing);
    const request = { batches, controller: new AbortController() };
    this.pending = request;
    return { kind: "load", request };
  }

  isCurrent(request: BuildingRequest): boolean {
    return this.pending === request && !request.controller.signal.aborted;
  }

  commit(request: BuildingRequest, batch: BuildingBatch): boolean {
    if (!this.isCurrent(request) || !request.batches.includes(batch)) return false;
    for (const tile of batch.tiles) this.loaded.set(tile.key, ++this.clock);
    if (request.batches.every((item) => item.tiles.every((tile) => this.loaded.has(tile.key)))) this.pending = null;
    return true;
  }

  evict(): string[] {
    const removed: string[] = [];
    const oldest = [...this.loaded].sort((a, b) => a[1] - b[1]);
    for (const [key] of oldest) {
      if (this.loaded.size <= this.limit) break;
      if (this.visible.has(key)) continue;
      this.loaded.delete(key);
      removed.push(key);
    }
    return removed;
  }

  fail(request: BuildingRequest): void { if (this.isCurrent(request)) this.cancelPending(); }
  cancelPending(): void { this.pending?.controller.abort(); this.pending = null; }
  clear(): void { this.cancelPending(); this.loaded.clear(); this.visible.clear(); }
}
