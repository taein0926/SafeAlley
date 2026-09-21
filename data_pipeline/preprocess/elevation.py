"""Estimate road grade from a user-supplied, documented high-resolution DEM.

This is terrain grade, not a measured wheelchair-accessible ramp grade.
"""

import json
from math import floor, isfinite
from pathlib import Path

from pyproj import CRS, Geod, Transformer
import rasterio
from rasterio.windows import Window


GEOD = Geod(ellps="WGS84")
MAX_CELL_SIZE_M = 10.0


class ElevationDataError(ValueError):
    """Raised when a DEM cannot support defensible pedestrian-grade estimates."""


def _bilinear_elevation(dem, x: float, y: float) -> float | None:
    """Sample four cell centres, rejecting nodata/out-of-bounds neighbours."""
    column, row = (~dem.transform) * (x, y)
    column -= 0.5
    row -= 0.5
    left, top = floor(column), floor(row)
    values = dem.read(1, window=Window(left, top, 2, 2), boundless=True, masked=True)
    if values.shape != (2, 2) or values.mask.any():
        return None
    dx, dy = column - left, row - top
    value = (
        float(values[0, 0]) * (1 - dx) * (1 - dy)
        + float(values[0, 1]) * dx * (1 - dy)
        + float(values[1, 0]) * (1 - dx) * dy
        + float(values[1, 1]) * dx * dy
    )
    return value if isfinite(value) else None


def calculate_road_slopes(
    roads_path: Path,
    dem_path: Path,
    output_path: Path,
    *,
    source_name: str,
    source_url: str,
    source_date: str,
    license_name: str,
) -> dict[str, int | float]:
    if not all((source_name, source_url, source_date, license_name)):
        raise ElevationDataError("DEM source, URL, date and license are required")
    roads = json.loads(roads_path.read_text(encoding="utf-8"))
    features = roads.get("features")
    if not isinstance(features, list) or not features:
        raise ElevationDataError("Road GeoJSON has no features")

    estimates: list[dict[str, object]] = []
    skipped_short = skipped_nodata = 0
    with rasterio.open(dem_path) as dem:
        if dem.count < 1 or dem.crs is None:
            raise ElevationDataError("DEM needs an elevation band and a declared CRS")
        if not dem.crs.is_projected:
            raise ElevationDataError("DEM must use a metre-based projected CRS")
        units = CRS.from_user_input(dem.crs).axis_info[0].unit_name.lower()
        if "metre" not in units and "meter" not in units:
            raise ElevationDataError("DEM horizontal units must be metres")
        cell_size_m = max(abs(dem.res[0]), abs(dem.res[1]))
        if cell_size_m > MAX_CELL_SIZE_M:
            raise ElevationDataError(
                f"DEM cell size {cell_size_m:g} m is too coarse for pedestrian routes; "
                f"maximum is {MAX_CELL_SIZE_M:g} m"
            )
        transformer = Transformer.from_crs("EPSG:4326", dem.crs, always_xy=True)
        for feature in features:
            properties = feature["properties"]
            coordinates = feature["geometry"]["coordinates"]
            first, last = coordinates[0], coordinates[-1]
            _, _, distance_m = GEOD.inv(first[0], first[1], last[0], last[1])
            if distance_m < 2 * cell_size_m:
                skipped_short += 1
                continue
            positions = [transformer.transform(*first[:2]), transformer.transform(*last[:2])]
            samples = [_bilinear_elevation(dem, *position) for position in positions]
            if any(sample is None for sample in samples):
                skipped_nodata += 1
                continue
            start_z, end_z = samples
            estimates.append(
                {
                    "source_id": properties["source_id"],
                    "incline_percent": round(abs(end_z - start_z) / distance_m * 100, 3),
                    "elevation_change_m": round(end_z - start_z, 3),
                }
            )

    result = {
        "metadata": {
            "source_name": source_name,
            "source_url": source_url,
            "source_date": source_date,
            "license": license_name,
            "cell_size_m": cell_size_m,
            "method": "endpoint terrain elevation difference / geodesic segment length",
            "warning": "Terrain grade is not a measured pavement or ramp grade",
        },
        "estimates": estimates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return {
        "estimated": len(estimates),
        "skipped_short": skipped_short,
        "skipped_nodata": skipped_nodata,
        "cell_size_m": cell_size_m,
    }
