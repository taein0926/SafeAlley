"""Build immutable XYZ PNG tiles once, not on each browser visit.

Run after replacing streetlight data (or changing this renderer). This is a
location-density visualization with a 45 m kernel, NOT measured illumination.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import zlib

import numpy as np

from loaders.postgis import database_connection

TILE_SIZE = 256
RADIUS_M = 45
MIN_ZOOM, MAX_ZOOM = 12, 17
RENDER_VERSION = "density-45m-v1"
SOURCE = "michuhol-public-data"


def pixel_position(lon, lat, zoom):
    scale = TILE_SIZE * 2 ** zoom
    lat_radians = math.radians(lat)
    return ((lon + 180) / 360 * scale,
            (1 - math.asinh(math.tan(lat_radians)) / math.pi) / 2 * scale)


def png_rgba(rgba):
    height, width, _ = rgba.shape
    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content))
    raw = b"".join(b"\x00" + row.tobytes() for row in rgba)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def tile_index(points, zoom):
    """Index every kernel into ALL intersecting tiles, so borders have no seams."""
    tiles = {}
    for lon, lat in points:
        x, y = pixel_position(lon, lat, zoom)
        radius = RADIUS_M * TILE_SIZE * 2 ** zoom / (40075016.686 * math.cos(math.radians(lat)))
        for ty in range(math.floor((y - radius) / TILE_SIZE), math.floor((y + radius) / TILE_SIZE) + 1):
            for tx in range(math.floor((x - radius) / TILE_SIZE), math.floor((x + radius) / TILE_SIZE) + 1):
                if 0 <= tx < 2 ** zoom and 0 <= ty < 2 ** zoom:
                    tiles.setdefault((tx, ty), []).append((x, y, radius))
    return tiles


def render_tile(tx, ty, kernels):
    alpha = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for x, y, radius in kernels:
        x -= tx * TILE_SIZE
        y -= ty * TILE_SIZE
        left, right = max(0, math.floor(x-radius)), min(TILE_SIZE, math.ceil(x+radius))
        top, bottom = max(0, math.floor(y-radius)), min(TILE_SIZE, math.ceil(y+radius))
        if left >= right or top >= bottom:
            continue
        yy, xx = np.mgrid[top:bottom, left:right]
        distance = np.sqrt((xx + 0.5 - x) ** 2 + (yy + 0.5 - y) ** 2) / radius
        alpha[top:bottom, left:right] += np.interp(distance, [0, .35, .75, 1], [.22, .12, .025, 0]) * 255
    source = np.minimum(255, alpha)
    display = np.where(source <= 20, 0, np.clip(np.floor((source - 20) * 1.8 + .5), 65, 150))
    fraction = np.clip((display - 50) / 100, 0, 1)
    colors = np.array([[72, 40, 120], [245, 162, 61], [184, 242, 90]], dtype=float)
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[:, :, channel] = np.where(display == 0, 0, np.interp(fraction, [0, .5, 1], colors[:, channel])).round()
    rgba[:, :, 3] = display
    return rgba


def build_tiles(points, root: Path):
    points = sorted((float(lon), float(lat)) for lon, lat in points)
    if not points or any(not (math.isfinite(lon) and math.isfinite(lat) and -180 < lon < 180 and -85 < lat < 85)
                         for lon, lat in points):
        raise ValueError("Expected nonempty, finite WGS84 streetlight positions")
    encoded = json.dumps([RENDER_VERSION, MIN_ZOOM, MAX_ZOOM, points], separators=(",", ":")).encode()
    version = hashlib.sha256(encoded).hexdigest()[:24]
    root.mkdir(parents=True, exist_ok=True)
    destination = root / version
    if not (destination / "manifest.json").is_file():
        # Failed builds never change the active manifest; published versions stay immutable.
        with tempfile.TemporaryDirectory(prefix="heatmap-build-", dir=root) as directory:
            stage = Path(directory)
            count = 0
            for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
                for (tx, ty), kernels in tile_index(points, zoom).items():
                    rgba = render_tile(tx, ty, kernels)
                    if not rgba[:, :, 3].any():
                        continue
                    path = stage / str(zoom) / str(tx) / f"{ty}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(png_rgba(rgba))
                    count += 1
            manifest = {
                "version": version, "minzoom": MIN_ZOOM, "maxzoom": MAX_ZOOM,
                "bounds": [min(p[0] for p in points) - .001, min(p[1] for p in points) - .001,
                           max(p[0] for p in points) + .001, max(p[1] for p in points) + .001],
                "point_count": len(points), "tile_count": count, "radius_m": RADIUS_M,
                "source": SOURCE, "renderer": RENDER_VERSION,
            }
            (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            # Rename into a NEW version directory; never overwrite an existing version.
            stage.rename(destination)
    manifest_bytes = (destination / "manifest.json").read_bytes()
    with tempfile.NamedTemporaryFile(dir=root, suffix=".json", delete=False) as handle:
        handle.write(manifest_bytes)
        manifest_temp = Path(handle.name)
    manifest_temp.replace(root / "manifest.json")
    return json.loads(manifest_bytes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(os.getenv("HEATMAP_TILE_ROOT", "/map-tiles/streetlights")))
    args = parser.parse_args()
    with database_connection() as connection:
        points = connection.execute("""
            SELECT ST_X(ST_Transform(geom,4326)), ST_Y(ST_Transform(geom,4326))
            FROM streetlights WHERE source = %s AND geom IS NOT NULL ORDER BY id
        """, (SOURCE,)).fetchall()
    print(json.dumps(build_tiles(points, args.output)))


if __name__ == "__main__":
    main()
