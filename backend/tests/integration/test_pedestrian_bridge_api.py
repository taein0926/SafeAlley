from fastapi.testclient import TestClient

from app.db.connection import connect_database
from app.main import app


def test_bridge_repository_filters_points_and_reports_actual_graph_links():
    response = TestClient(app).get("/api/pedestrian-bridges")
    assert response.status_code == 200
    data = response.json()
    with connect_database() as connection:
        expected = connection.execute("SELECT id FROM pedestrian_references WHERE kind='bridge'").fetchall()
        linked = connection.execute("""SELECT DISTINCT jsonb_array_elements_text(
            properties->'pedestrian_reference'->'bridge_ids') FROM road_segments WHERE source='osm'""").fetchall()
    assert {item["id"] for item in data["features"]} == {row[0] for row in expected}
    linked_ids = {row[0] for row in linked}
    assert data["metadata"]["count"] == len(expected)
    assert data["metadata"]["routing_connected_count"] == len({row[0] for row in expected} & linked_ids)
    for item in data["features"]:
        assert item["geometry"]["type"] == "Point"
        longitude, latitude = item["geometry"]["coordinates"]
        assert -180 <= longitude <= 180 and -90 <= latitude <= 90
        assert item["properties"]["kind"] == "bridge"
        assert item["properties"]["routing_connected"] == (item["id"] in linked_ids)
