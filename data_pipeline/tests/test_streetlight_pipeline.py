import json

import pytest

from preprocess.streetlights import (
    StreetlightPreprocessError,
    preprocess_streetlights,
)


def test_cp949_streetlight_csv_is_converted_to_wgs84_geojson(tmp_path) -> None:
    source = tmp_path / "streetlights.csv"
    output = tmp_path / "streetlights.geojson"
    source.write_text(
        "가로등주명,소속 분전함,표찰번호,경도,위도\n"
        "주안1,A함,A-1,126.68,37.46\n"
        "주안2,A함,A-2,126.681,37.461\n",
        encoding="cp949",
    )

    stats = preprocess_streetlights(
        source,
        output,
        source="test-source",
        source_dataset="test-dataset",
    )
    document = json.loads(output.read_text(encoding="utf-8"))
    assert stats["count"] == 2
    assert document["metadata"]["crs"] == "EPSG:4326"
    assert document["features"][0]["geometry"] == {
        "type": "Point",
        "coordinates": [126.68, 37.46],
    }


def test_streetlight_csv_rejects_coordinates_outside_korea(tmp_path) -> None:
    source = tmp_path / "invalid.csv"
    source.write_text(
        "가로등주명,소속 분전함,표찰번호,경도,위도\n"
        "오류,A함,A-1,0,0\n",
        encoding="cp949",
    )
    with pytest.raises(StreetlightPreprocessError, match="outside"):
        preprocess_streetlights(
            source,
            tmp_path / "output.geojson",
            source="test-source",
            source_dataset="test-dataset",
        )
