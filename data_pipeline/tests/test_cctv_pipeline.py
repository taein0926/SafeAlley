import json

from preprocess.cctvs import preprocess_cctvs, validate_cctv_geojson


def test_cctv_preprocess_preserves_all_rows_and_reports_coordinates(tmp_path) -> None:
    source = tmp_path / "raw.json"
    output = tmp_path / "processed.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {"설치목적구분": "방범", "경도": "126.68", "위도": "37.46"},
                    {"설치목적구분": "교통", "경도": None, "위도": None},
                    {"설치목적구분": "방범", "경도": "999", "위도": "37.46"},
                    {"설치목적구분": "방범", "경도": "126.68", "위도": "37.46"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    stats = preprocess_cctvs(source, output, safety_purposes={"방범"})
    document = json.loads(output.read_text(encoding="utf-8"))

    assert stats["purpose_counts"] == {"교통": 1, "방범": 3}
    assert stats["safety_cctv_count"] == 3
    assert stats["coordinate_present_count"] == 2
    assert stats["coordinate_null_count"] == 1
    assert stats["coordinate_invalid_count"] == 1
    assert len(document["records"]) == 4
    assert len({row["source_id"] for row in document["records"]}) == 4
    assert document["records"][1]["longitude"] is None
    assert document["records"][2]["coordinate_status"] == "out_of_korea_range"


def test_cctv_purpose_is_not_guessed(tmp_path) -> None:
    source = tmp_path / "raw.json"
    output = tmp_path / "processed.json"
    source.write_text(
        json.dumps({"records": [{"설치목적구분": "생활안전", "경도": 126.68, "위도": 37.46}]}),
        encoding="utf-8",
    )
    stats = preprocess_cctvs(source, output, safety_purposes=set())
    assert stats["safety_cctv_count"] == 0


def test_ai_ready_cctv_geojson_is_validated_without_purpose_refilter(tmp_path) -> None:
    source = tmp_path / "cctv.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [126.68, 37.46]},
                        "properties": {
                            "관리번호": "CCTV-1",
                            "설치목적구분": "생활방범",
                            "설치연월": "2024-01",
                            "관리기관명": "미추홀구",
                        },
                    },
                    {
                        "type": "Feature",
                        "id": "bad-coordinate",
                        "geometry": {"type": "Point", "coordinates": [999, 37.46]},
                        "properties": {},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows, stats = validate_cctv_geojson(source)
    assert stats["total_feature_count"] == 2
    assert stats["valid_feature_count"] == 1
    assert stats["excluded_features"] == [
        {"identifier": "bad-coordinate", "reason": "invalid_longitude"}
    ]
    assert rows[0]["source_id"] == "CCTV-1"
    assert rows[0]["installed_at"] == "2024-01"
    assert rows[0]["is_safety_cctv"] is True
