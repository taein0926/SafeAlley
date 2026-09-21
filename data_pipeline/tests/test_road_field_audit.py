import json

from analysis.road_quality import audit_road_network


def test_field_audit_exports_only_unverified_major_road_edges(tmp_path) -> None:
    roads_path = tmp_path / "roads.geojson"
    cases_path = tmp_path / "cases.json"
    output_path = tmp_path / "audit.geojson"
    roads_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
            [126.68, 37.46], [126.681, 37.46]
        ]}, "properties": {"source_id": "fallback-1", "source_node_id": 1,
                           "target_node_id": 2, "walkability_class": "major_road_fallback",
                           "walkability_factor": 1}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
            [126.681, 37.46], [126.682, 37.46]
        ]}, "properties": {"source_id": "footway-1", "source_node_id": 2,
                           "target_node_id": 3, "walkability_class": "pedestrian_only",
                           "walkability_factor": 1}},
    ]}), encoding="utf-8")
    cases_path.write_text(json.dumps([
        {"name": "case-a", "origin": [126.68, 37.46],
         "destination": [126.682, 37.46]},
        {"name": "case-b", "origin": [126.68, 37.46],
         "destination": [126.681, 37.46]},
    ]), encoding="utf-8")

    report = audit_road_network(roads_path, cases_path, output_path)
    audit = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["passed"] == 2
    assert report["field_audit_unique_edges"] == 1
    assert audit["metadata"]["status"] == "not_field_verified"
    feature = audit["features"][0]
    assert feature["properties"]["affected_routes"] == ["case-a", "case-b"]
    assert feature["properties"]["field_status"] == "unverified"
    assert feature["properties"]["check_legal_crossing"] is None
