"""Read prebuilt visualization assets. No collection, rasterization or DB queries."""
import json
import os
from pathlib import Path
import re


def heatmap_root() -> Path:
    return Path(os.getenv("HEATMAP_TILE_ROOT", "/map-tiles/streetlights"))


def heatmap_manifest() -> dict:
    return json.loads((heatmap_root() / "manifest.json").read_text(encoding="utf-8"))


def heatmap_tile(version: str, z: int, x: int, y: int) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{24}", version) or not 0 <= z <= 20 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("Invalid tile coordinates/version")
    root = heatmap_root() / version
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["minzoom"] <= z <= manifest["maxzoom"]:
        raise ValueError("Unsupported tile zoom")
    path = root / str(z) / str(x) / f"{y}.png"
    return path if path.is_file() else None
