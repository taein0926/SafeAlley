import json

from collectors.osm import build_overpass_query
from preprocess.osm_roads import preprocess_osm_roads, safety_score_for_segment
from preprocess.roads import read_road_features


def test_overpass_query_filters_michuhol_administrative_area() -> None:
    query = build_overpass_query("미추홀구", "6")

    assert '["boundary"="administrative"]' in query
    assert '["admin_level"="6"]' in query
    assert '["name"="미추홀구"]' in query
    assert 'way["highway"](area.searchArea)' in query


def test_preprocess_builds_walkable_graph_edges(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSM_DEFAULT_SAFETY_SCORE", "50")
    monkeypatch.setenv("OSM_SAFETY_SCORE_MODE", "uniform")
    monkeypatch.setenv("OSM_MIN_SEGMENT_LENGTH_M", "1")
    raw_path = tmp_path / "raw.json"
    processed_path = tmp_path / "processed.geojson"
    raw_path.write_text(
        json.dumps(
            {
                "elements": [
                    {"type": "node", "id": 1, "lat": 37.46, "lon": 126.68},
                    {"type": "node", "id": 2, "lat": 37.461, "lon": 126.68},
                    {"type": "node", "id": 3, "lat": 37.462, "lon": 126.68},
                    {"type": "node", "id": 4, "lat": 37.462, "lon": 126.681},
                    {
                        "type": "way",
                        "id": 100,
                        "nodes": [1, 2, 3],
                        "tags": {"highway": "residential", "name": "테스트길"},
                    },
                    {
                        "type": "way",
                        "id": 200,
                        "nodes": [1, 4],
                        "tags": {"highway": "motorway"},
                    },
                    {
                        "type": "way",
                        "id": 300,
                        "nodes": [1, 4],
                        "tags": {"highway": "footway", "foot": "no"},
                    },
                    {
                        "type": "way",
                        "id": 400,
                        "nodes": [3, 4],
                        "tags": {"highway": "footway", "oneway:foot": "-1"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    stats = preprocess_osm_roads(raw_path, processed_path)
    features = read_road_features(processed_path)

    assert stats == {
        "raw_nodes": 4,
        "raw_ways": 4,
        "walkable_ways": 2,
        "road_segments": 3,
        "skipped_edges": 0,
    }
    assert [feature["properties"]["source_id"] for feature in features] == [
        "osm-way-100-edge-1",
        "osm-way-100-edge-2",
        "osm-way-400-edge-1",
    ]
    assert features[0]["properties"]["source_node_id"] == 1
    assert features[0]["properties"]["target_node_id"] == 2
    assert features[0]["properties"]["streetlight_score"] == 50
    assert features[2]["properties"]["forward_allowed"] is False
    assert features[2]["properties"]["reverse_allowed"] is True


def test_demo_safety_scores_are_stable_and_cover_all_color_bands() -> None:
    source_ids = [f"osm-way-{way_id}-edge-1" for way_id in range(300)]
    first_scores = [
        safety_score_for_segment(source_id, "demo") for source_id in source_ids
    ]
    second_scores = [
        safety_score_for_segment(source_id, "demo") for source_id in source_ids
    ]

    assert first_scores == second_scores
    assert any(score <= 54 for score in first_scores)
    assert any(55 <= score <= 74 for score in first_scores)
    assert any(score >= 75 for score in first_scores)


def test_preprocess_preserves_stairs_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSM_DEFAULT_SAFETY_SCORE", "50")
    monkeypatch.setenv("OSM_SAFETY_SCORE_MODE", "uniform")
    monkeypatch.setenv("OSM_MIN_SEGMENT_LENGTH_M", "1")
    raw_path = tmp_path / "stairs.json"
    processed_path = tmp_path / "stairs.geojson"
    raw_path.write_text(
        json.dumps(
            {
                "elements": [
                    {"type": "node", "id": 1, "lat": 37.46, "lon": 126.68},
                    {"type": "node", "id": 2, "lat": 37.461, "lon": 126.68},
                    {"type": "node", "id": 3, "lat": 37.462, "lon": 126.68},
                    {
                        "type": "way",
                        "id": 100,
                        "nodes": [1, 2],
                        "tags": {
                            "highway": "steps",
                            "step_count": "18",
                            "incline": "up",
                        },
                    },
                    {
                        "type": "way",
                        "id": 200,
                        "nodes": [2, 3],
                        "tags": {"highway": "footway"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    preprocess_osm_roads(raw_path, processed_path)
    stairs, footway = read_road_features(processed_path)

    assert stairs["properties"]["highway"] == "steps"
    assert stairs["properties"]["is_steps"] is True
    assert stairs["properties"]["step_count"] == "18"
    assert stairs["properties"]["incline"] == "up"
    assert stairs["properties"]["ramp"] is None
    assert stairs["properties"]["wheelchair"] is None
    assert stairs["properties"]["handrail"] is None
    assert footway["properties"]["highway"] == "footway"
    assert footway["properties"]["is_steps"] is False
    assert footway["properties"]["step_count"] is None
    assert footway["properties"]["incline"] is None
