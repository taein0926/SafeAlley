from fastapi.testclient import TestClient

from app.main import app


def test_retired_inspection_endpoints_are_not_registered():
    with TestClient(app) as client:
        for path in ("/api/osm-roads", "/api/crossings"):
            assert client.get(path).status_code == 404


def test_active_map_and_route_endpoints_remain_registered():
    paths = app.openapi()["paths"]
    for path in (
        "/api/roads", "/api/safety/roads", "/api/buildings", "/api/streetlights",
        "/api/cctvs", "/api/help-points", "/api/pedestrian-bridges",
        "/api/streetlight-heatmap/manifest", "/api/routes/shortest",
        "/api/routes/safe", "/api/agent/query",
    ):
        assert path in paths
