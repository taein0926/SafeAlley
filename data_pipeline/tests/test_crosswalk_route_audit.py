import json

from analysis.crosswalk_quality import audit_route_crosswalks


def test_crosswalk_audit_keeps_proximity_separate_from_graph_connection(tmp_path) -> None:
    road = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [
            [126.68, 37.46], [126.681, 37.46],
        ]},
        "properties": {
            "source_id": "osm-edge-1", "source_node_id": 1,
            "target_node_id": 2, "crossing_node_ids": [1],
        },
    }
    crosswalk_path = tmp_path / "official.geojson"
    output_path = tmp_path / "review.geojson"
    crosswalk_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {"source": "official-test", "reference_date": "2022-10-31"},
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [126.68, 37.46]},
             "properties": {"source_id": "on-tagged-node"}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [126.6805, 37.46]},
             "properties": {"source_id": "mid-edge-only"}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [126.69, 37.46]},
             "properties": {"source_id": "far-away"}},
        ],
    }), encoding="utf-8")

    stats = audit_route_crosswalks(
        [road], {"demo": [(road["properties"], road["geometry"])]},
        crosswalk_path, output_path,
    )
    review = json.loads(output_path.read_text(encoding="utf-8"))
    by_id = {feature["properties"]["source_id"]: feature["properties"]
             for feature in review["features"]}

    assert stats["crosswalk_review_candidates"] == 2
    assert by_id["on-tagged-node"]["network_review_status"] == "mapped_on_route"
    assert by_id["mid-edge-only"]["network_review_status"] == "needs_connection_review"
    assert by_id["mid-edge-only"]["check_legal_crossing"] is None
    assert by_id["mid-edge-only"]["field_status"] == "unverified"
    assert "far-away" not in by_id
    assert road["properties"]["crossing_node_ids"] == [1]
