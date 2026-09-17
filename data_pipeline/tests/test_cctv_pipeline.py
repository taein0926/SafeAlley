import json

from preprocess.cctvs import preprocess_cctvs


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
