from pathlib import Path

import pytest

from preprocess.public_streetlights import preprocess_incheon_streetlights


RAW = Path(__file__).parents[1] / "raw" / "public_pedestrian" / "incheon_road_facilities_3d_poi_20221031.zip"


@pytest.mark.skipif(not RAW.exists(), reason="official source ZIP is not checked into Git")
def test_official_michuhol_streetlight_extract(tmp_path):
    stats = preprocess_incheon_streetlights(RAW, tmp_path / "streetlights.geojson")
    assert stats["streetlights"] == 3884
