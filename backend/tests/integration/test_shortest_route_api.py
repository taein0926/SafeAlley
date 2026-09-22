from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_shortest_route_uses_sample_graph() -> None:
    response = client.post(
        "/api/routes/shortest",
        json={
            "start": {"latitude": 37.4608, "longitude": 126.6790},
            "end": {"latitude": 37.4608, "longitude": 126.6810},
            "source": "test-fixture",
        },
    )

    assert response.status_code == 200
    route = response.json()
    assert route["type"] == "Feature"
    assert route["geometry"]["type"] == "LineString"
    assert route["properties"]["route_type"] == "shortest"
    assert route["properties"]["crs"] == "EPSG:4326"
    assert route["properties"]["start_node_id"] == 9001
    assert route["properties"]["end_node_id"] == 9002
    assert route["properties"]["total_distance_m"] > 0
    assert route["properties"]["average_safety_score"] is not None
    assert [
        segment["source_id"]
        for segment in route["properties"]["road_segments"]
    ] == ["test-road-001"]
    assert route["properties"]["cost_weights"]["stairs"] == 0
    assert route["properties"]["stairs_segment_count"] == 1
    assert route["properties"]["road_segments"][0]["highway"] == "steps"
    assert len(route["properties"]["road_segments"][0]["coordinates"]) >= 2
    assert route["properties"]["road_segments"][0]["is_steps"] is True
    assert route["properties"]["road_segments"][0]["incline"] == "up"
    assert route["properties"]["road_segments"][0]["stairs_penalty"] == 0


def test_safe_route_is_comparable_and_chooses_safer_sample_segments() -> None:
    request = {
        "start": {"latitude": 37.4608, "longitude": 126.6790},
        "end": {"latitude": 37.4608, "longitude": 126.6830},
        "source": "test-fixture",
    }

    shortest_response = client.post("/api/routes/shortest", json=request)
    safe_response = client.post("/api/routes/safe", json=request)

    assert shortest_response.status_code == 200
    assert safe_response.status_code == 200

    shortest = shortest_response.json()
    safe = safe_response.json()
    assert shortest["properties"]["route_type"] == "shortest"
    assert safe["properties"]["route_type"] == "safe"
    assert shortest["properties"]["start_node_id"] == safe["properties"]["start_node_id"]
    assert shortest["properties"]["end_node_id"] == safe["properties"]["end_node_id"]
    assert safe["properties"]["total_distance_m"] > shortest["properties"]["total_distance_m"]
    assert (
        safe["properties"]["average_safety_score"]
        > shortest["properties"]["average_safety_score"]
    )
    assert [
        segment["source_id"]
        for segment in shortest["properties"]["road_segments"]
    ] == ["test-road-001", "test-road-002"]
    assert [
        segment["source_id"]
        for segment in safe["properties"]["road_segments"]
    ] == ["test-road-003", "test-road-004"]


def test_shortest_route_can_avoid_steps_with_stairs_weight() -> None:
    request = {
        "start": {"latitude": 37.4608, "longitude": 126.6790},
        "end": {"latitude": 37.4608, "longitude": 126.6830},
        "source": "test-fixture",
    }

    default_route = client.post("/api/routes/shortest", json=request).json()
    zero_weight_route = client.post(
        "/api/routes/shortest",
        json={**request, "stairs_weight": 0.0},
    ).json()
    avoided_route = client.post(
        "/api/routes/shortest",
        json={**request, "stairs_weight": 1.0},
    ).json()

    assert zero_weight_route == default_route
    assert default_route["properties"]["stairs_segment_count"] == 2
    assert avoided_route["properties"]["stairs_segment_count"] == 0
    assert avoided_route["properties"]["total_distance_m"] > default_route["properties"]["total_distance_m"]
    assert avoided_route["properties"]["cost_weights"]["stairs"] == 1.0
    assert [
        segment["source_id"]
        for segment in avoided_route["properties"]["road_segments"]
    ] == ["test-road-003", "test-road-004"]


def test_stairs_weight_request_validation() -> None:
    request = {
        "start": {"latitude": 37.4608, "longitude": 126.6790},
        "end": {"latitude": 37.4608, "longitude": 126.6830},
        "source": "test-fixture",
    }

    assert client.post(
        "/api/routes/shortest",
        json={**request, "stairs_weight": -0.01},
    ).status_code == 422
    assert client.post(
        "/api/routes/shortest",
        json={**request, "stairs_weight": 1.01},
    ).status_code == 422
