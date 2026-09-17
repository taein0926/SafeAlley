import json

import pytest

from preprocess.buildings import BuildingPreprocessError, preprocess_buildings


def source_collection() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [126.6800, 37.4610],
                        [126.6802, 37.4610],
                        [126.6802, 37.4612],
                        [126.6800, 37.4612],
                        [126.6800, 37.4610],
                    ]],
                },
                "properties": {
                    "GU_NAME": "미추홀구",
                    "BULD_PK": "A-1",
                    "BULD_NM": "테스트 건물",
                    "ARCH_AREA": "123.4",
                    "HEIGHT": "",
                },
            },
            {
                "type": "Feature",
                "id": "2",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[
                        126.6810,
                        37.4610,
                    ], [
                        126.6812,
                        37.4610,
                    ], [
                        126.6812,
                        37.4612,
                    ], [
                        126.6810,
                        37.4612,
                    ], [
                        126.6810,
                        37.4610,
                    ]]]],
                },
                "properties": {"GU_NAME": "남동구", "BULD_PK": "B-1"},
            },
        ],
    }


def test_building_preprocess_filters_and_normalizes_polygon(tmp_path) -> None:
    source_path = tmp_path / "buildings.geojson"
    output_path = tmp_path / "processed.geojson"
    source_path.write_text(
        json.dumps(source_collection(), ensure_ascii=False),
        encoding="utf-8",
    )

    stats = preprocess_buildings(
        source_path,
        output_path,
        source="imap",
        source_dataset="test dataset",
        district_field="GU_NAME",
    )

    assert stats == {"input_features": 2, "output_buildings": 1}
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["metadata"]["crs"] == "EPSG:4326"
    feature = result["features"][0]
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert feature["properties"]["building_id"] == "A-1"
    assert feature["properties"]["building_area"] == pytest.approx(123.4)
    assert feature["properties"]["height_m"] is None


def test_building_preprocess_requires_explicit_michuhol_filter(tmp_path) -> None:
    source_path = tmp_path / "buildings.geojson"
    source_path.write_text(json.dumps(source_collection()), encoding="utf-8")

    with pytest.raises(BuildingPreprocessError, match="--boundary"):
        preprocess_buildings(
            source_path,
            tmp_path / "processed.geojson",
            source="imap",
            source_dataset="test dataset",
        )


def test_building_preprocess_can_join_mapped_address_fields(tmp_path) -> None:
    source_path = tmp_path / "buildings.geojson"
    output_path = tmp_path / "processed.geojson"
    field_map_path = tmp_path / "field-map.json"
    collection = source_collection()
    collection["features"][0]["properties"].update(
        {"LEGAL_DONG": "인천광역시 미추홀구 주안동", "LOT": "30-2"}
    )
    source_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    field_map_path.write_text(
        json.dumps({"address": ["LEGAL_DONG", "LOT"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    preprocess_buildings(
        source_path,
        output_path,
        source="molit-gis-building",
        source_dataset="test dataset",
        district_field="GU_NAME",
        field_map_path=field_map_path,
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["features"][0]["properties"]["address"] == (
        "인천광역시 미추홀구 주안동 30-2"
    )
