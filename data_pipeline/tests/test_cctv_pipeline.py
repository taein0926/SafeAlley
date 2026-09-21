import json

from preprocess.cctvs import preprocess_cctv_csv, preprocess_cctvs


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
    assert stats["coordinate_quality_counts"] == {
        "source_approximate": 2,
        "unusable": 2,
    }
    assert document["records"][0]["coordinate_quality"] == "source_approximate"
    assert document["records"][0]["longitude_precision_digits"] == 2


def test_cctv_preprocess_marks_high_precision_source_coordinates(tmp_path) -> None:
    source = tmp_path / "raw.json"
    output = tmp_path / "processed.json"
    source.write_text(json.dumps({"records": [{
        "설치목적구분": "방범", "경도": "126.68012", "위도": "37.46123",
    }]}, ensure_ascii=False), encoding="utf-8")

    stats = preprocess_cctvs(source, output, safety_purposes={"방범"})
    row = json.loads(output.read_text(encoding="utf-8"))["records"][0]

    assert stats["coordinate_quality_counts"] == {"source_precise": 1}
    assert row["coordinate_quality"] == "source_precise"
    assert row["longitude_precision_digits"] == 5
    assert row["latitude_precision_digits"] == 5


def test_cctv_purpose_is_not_guessed(tmp_path) -> None:
    source = tmp_path / "raw.json"
    output = tmp_path / "processed.json"
    source.write_text(
        json.dumps({"records": [{"설치목적구분": "생활안전", "경도": 126.68, "위도": 37.46}]}),
        encoding="utf-8",
    )
    stats = preprocess_cctvs(source, output, safety_purposes=set())
    assert stats["safety_cctv_count"] == 0


def test_national_cctv_csv_filters_district_and_uses_management_id(tmp_path) -> None:
    source = tmp_path / "national.csv"
    output = tmp_path / "processed.json"
    source.write_text(
        "관리번호,관리기관명,소재지도로명주소,설치목적구분,WGS84위도,WGS84경도\n"
        "cctv-1,인천광역시 미추홀구청,인천광역시 미추홀구 주안로,생활방범,37.46,126.68\n"
        "cctv-2,서울특별시청,서울특별시 중구 세종대로,생활방범,37.56,126.97\n",
        encoding="cp949",
    )

    stats = preprocess_cctv_csv(
        source,
        output,
        district_name="미추홀구",
        safety_purposes={"생활방범"},
    )
    document = json.loads(output.read_text(encoding="utf-8"))

    assert stats["total_count"] == 1
    assert stats["safety_cctv_count"] == 1
    assert document["records"][0]["source_id"] == "cctv-1"
    assert document["records"][0]["longitude"] == 126.68
