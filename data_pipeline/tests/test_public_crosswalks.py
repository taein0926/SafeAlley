import json
from pathlib import Path

import pytest

from preprocess.public_crosswalks import preprocess_incheon_crosswalks


OFFICIAL_ZIP = (
    Path(__file__).resolve().parents[1] / "raw" / "public_pedestrian"
    / "incheon_road_facilities_3d_poi_20221031.zip"
)


@pytest.mark.skipif(not OFFICIAL_ZIP.exists(), reason="Official source ZIP is not checked into Git")
def test_official_incheon_crosswalks_are_filtered_and_transformed(tmp_path) -> None:
    output = tmp_path / "crosswalks.geojson"
    stats = preprocess_incheon_crosswalks(OFFICIAL_ZIP, output)
    document = json.loads(output.read_text(encoding="utf-8"))
    assert stats["crosswalks"] == 839
    assert len(document["features"]) == 839
    assert all(feature["properties"]["district"] == "미추홀구" for feature in document["features"])
    assert all(feature["geometry"]["type"] == "Point" for feature in document["features"])
    assert all(126.55 <= feature["geometry"]["coordinates"][0] <= 126.8
               for feature in document["features"])
