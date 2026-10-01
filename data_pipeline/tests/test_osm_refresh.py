import json

import pytest

from loaders.osm_refresh import validate_snapshot, snapshot_crossings, VERSION
from preprocess.osm_roads import preprocess_osm_roads
from preprocess.osm_pedestrian import pedestrian_metadata


def test_refresh_rejects_bbox_only_or_partial_response():
    doc = {"osm3s": {"timestamp_osm_base": "2026-10-01T00:00:00Z"},
           "elements": [{"type": "way", "id": 1}]}
    meta = {"area_name": "미추홀구", "admin_level": "6",
            "query": 'way["highway"](area.searchArea);node["highway"="crossing"](area.searchArea);'}
    assert validate_snapshot(doc, meta) == "2026-10-01T00:00:00Z"
    with pytest.raises(ValueError):
        validate_snapshot({**doc, "remark": "timeout"}, meta)
    with pytest.raises(ValueError):
        validate_snapshot(doc, {**meta, "query": 'way["highway"](37,126,38,127);'})


def test_crossing_tags_survive_duplicate_skeleton_nodes():
    point = {"type": "node", "id": 12, "lat": 37.4, "lon": 126.6,
             "tags": {"highway": "crossing"}}
    assert snapshot_crossings({"elements": [point, {**point, "tags": {}}]}) == {12: point}


def test_refresh_keeps_submetre_osm_connections(tmp_path, monkeypatch):
    monkeypatch.setenv("OSM_MIN_SEGMENT_LENGTH_M", "0")
    monkeypatch.setenv("OSM_SAFETY_SCORE_MODE", "uniform")
    doc = {"elements": [
        {"type": "node", "id": 1, "lon": 126.66, "lat": 37.46},
        {"type": "node", "id": 2, "lon": 126.660005, "lat": 37.46},
        {"type": "way", "id": 3, "nodes": [1,2], "tags": {"highway": "footway"}},
    ]}
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert preprocess_osm_roads(path, tmp_path/"out.json")["road_segments"] == 1
    metadata = pedestrian_metadata(doc, [dict(id=5,source_node_id=1,target_node_id=2,
        length_m=0.4,properties={"osm_way_id":3})], version=VERSION)
    assert metadata[5]["version"] == "osm-pedestrian-michuhol-v2"
    assert metadata[5]["allowed"]
