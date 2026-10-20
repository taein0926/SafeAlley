"""기본 출처와 잘못된 대체 적재를 검사하며 실제 DB에는 연결하지 않는다."""
import argparse
import json
from unittest.mock import patch

import pytest

import cli
from loaders import buildings


def building_arguments(source=None):
    return argparse.Namespace(
        input="official.geojson", source=source, source_dataset="공식 건물 시험 자료",
        boundary=None, district_field=None, district_value="미추홀구",
        assume_michuhol_only=True, source_crs=None, boundary_crs=None,
        field_map=None, source_encoding=None,
    )


@pytest.mark.parametrize("source,expected", [(None, "molit-gis-building"), ("imap", "imap")])
def test_building_preprocess_preserves_explicit_source_and_defaults_to_molit(source, expected):
    with patch.object(cli, "preprocess_buildings", return_value={"input_features": 1, "output_buildings": 1}) as preprocess:
        cli.preprocess_building_file(building_arguments(source))
    assert preprocess.call_args.kwargs["source"] == expected


@pytest.mark.parametrize("source,expected", [(None, "molit-gis-building"), ("imap", "imap")])
def test_building_load_uses_same_source_without_connecting_database(source, expected):
    with patch.object(cli, "load_buildings", return_value=1) as load:
        cli.load_building_file(building_arguments(source))
    load.assert_called_once_with(cli.PROCESSED_BUILDINGS_PATH, replace_source=expected)


def processed_buildings(tmp_path, source):
    path = tmp_path / "buildings.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection", "metadata": {"crs": "EPSG:4326"},
        "features": [{
            "properties": {"source": source, "building_id": "test-building"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [126.68, 37.46], [126.681, 37.46], [126.681, 37.461], [126.68, 37.46],
            ]]},
        }],
    }), encoding="utf-8")
    return path


@pytest.mark.parametrize("source,target", [("imap", "molit-gis-building"), ("molit-gis-building", "imap")])
def test_mismatched_source_stops_before_any_database_connection(tmp_path, source, target):
    path = processed_buildings(tmp_path, source)
    with patch.object(buildings, "database_connection") as connect:
        with pytest.raises(buildings.BuildingLoadError, match="source"):
            buildings.load_buildings(path, replace_source=target)
    connect.assert_not_called()


@pytest.mark.parametrize("source", ["molit-gis-building", "imap"])
def test_matching_source_loads_only_through_mock_database(tmp_path, source):
    path = processed_buildings(tmp_path, source)
    with patch.object(buildings, "database_connection") as connect:
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        assert buildings.load_buildings(path, replace_source=source) == 1
    assert cursor.execute.call_args_list[0].args == ("DELETE FROM buildings WHERE source = %s", (source,))
    assert cursor.execute.call_args_list[1].args[1][1] == source
