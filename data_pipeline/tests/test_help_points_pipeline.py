import json

from preprocess.help_points import validate_help_points


def test_help_point_validation_uses_geometry_and_reports_exact_exclusions(tmp_path) -> None:
    source = tmp_path / "help.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "police-1",
                        "geometry": {"type": "Point", "coordinates": [126.68, 37.46]},
                        "properties": {
                            "name": "경찰시설",
                            "category": "police",
                            "longitude": 127.0,
                            "latitude": 38.0,
                        },
                    },
                    {
                        "type": "Feature",
                        "id": "bad-line",
                        "geometry": {"type": "LineString", "coordinates": []},
                        "properties": {},
                    },
                    {
                        "type": "Feature",
                        "id": "bad-null",
                        "geometry": None,
                        "properties": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    rows, stats = validate_help_points(source)
    assert len(rows) == 1
    assert rows[0]["longitude"] == 126.68
    assert rows[0]["latitude"] == 37.46
    assert rows[0]["category"] == "police"
    assert stats["category_counts"] == {"police": 1}
    assert [item["reason"] for item in stats["excluded_features"]] == [
        "not_point",
        "geometry_null",
    ]
    assert len(stats["warnings"]) == 1
