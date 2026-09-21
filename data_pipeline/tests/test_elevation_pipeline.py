import json

import numpy as np
from pyproj import Transformer
import pytest
import rasterio
from rasterio.transform import from_origin

from preprocess.elevation import ElevationDataError, calculate_road_slopes


def _roads(path):
    to_wgs84 = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
    start = to_wgs84.transform(900005, 1950000)
    end = to_wgs84.transform(900035, 1950000)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"source_id": "edge-1"},
        "geometry": {"type": "LineString", "coordinates": [start, end]},
    }]}), encoding="utf-8")


def _dem(path, cell_size=5, driver="GTiff"):
    with rasterio.open(
        path, "w", driver=driver, width=20, height=20, count=1,
        dtype="float32", crs="EPSG:5179",
        transform=from_origin(900000, 1950050, cell_size, cell_size),
        nodata=-9999,
    ) as dataset:
        dataset.write(np.tile(np.arange(20, dtype="float32") * .5, (20, 1)), 1)


def test_dem_grade_estimate_and_provenance(tmp_path):
    roads, dem, output = (tmp_path / name for name in ("roads.geojson", "dem.tif", "slopes.json"))
    _roads(roads)
    _dem(dem)
    stats = calculate_road_slopes(
        roads, dem, output, source_name="test high-resolution DEM",
        source_url="https://example.org/dem", source_date="2026-01-01",
        license_name="test-license",
    )
    assert stats["estimated"] == 1
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["metadata"]["cell_size_m"] == 5
    assert document["estimates"][0]["incline_percent"] == pytest.approx(10, abs=.2)


def test_coarse_dem_is_rejected(tmp_path):
    roads, dem, output = (tmp_path / name for name in ("roads.geojson", "coarse.tif", "slopes.json"))
    _roads(roads)
    _dem(dem, cell_size=30)
    with pytest.raises(ElevationDataError, match="too coarse"):
        calculate_road_slopes(
            roads, dem, output, source_name="test", source_url="https://example.org",
            source_date="2026-01-01", license_name="test",
        )


def test_gdal_hfa_img_can_be_used_without_conversion(tmp_path):
    roads, dem, output = (tmp_path / name for name in ("roads.geojson", "dem.img", "slopes.json"))
    _roads(roads)
    _dem(dem, driver="HFA")
    stats = calculate_road_slopes(
        roads, dem, output, source_name="test IMG DEM",
        source_url="https://example.org/dem", source_date="2026-01-01",
        license_name="test-license",
    )
    assert stats["estimated"] == 1
