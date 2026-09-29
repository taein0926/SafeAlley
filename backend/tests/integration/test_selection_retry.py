from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import httpx
import pytest
from psycopg import sql
from fastapi.testclient import TestClient

from app.db.connection import connect_database
from app.main import app
from app.repositories.personalization_repository import save_recommendation
from app.services import personalization_service


@pytest.fixture
def feedback():
    user = f"test-selection-retry-{uuid4()}"
    recommendation = save_recommendation(user, [
        {"route_type": name, "metrics": {"distance_m": distance}}
        for name, distance in [("shortest", 100), ("safe", 200)]
    ])
    try:
        yield {"recommendation_id": recommendation, "user_id": user, "selected_route_type": "safe"}
    finally:
        with connect_database() as connection:
            for table in ("route_selection_events", "route_recommendations", "user_route_preferences"):
                connection.execute(sql.SQL("DELETE FROM {} WHERE user_id = %s").format(sql.Identifier(table)), (user,))


def test_concurrent_retries_learn_once_and_changed_selection_still_learns(feedback):
    def send(_):
        with TestClient(app) as client:
            return client.post("/api/agent/route-selections", json=feedback)

    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(send, range(3)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["preferences"][0]["observations"] == 1 for response in responses)
    with TestClient(app) as client:
        changed = client.post("/api/agent/route-selections", json={**feedback, "selected_route_type": "shortest"})
    assert changed.status_code == 200
    assert changed.json()["preferences"][0]["observations"] == 2


def test_learning_failure_rolls_back_selection_so_retry_can_recover(feedback, monkeypatch):
    original = personalization_service.upsert_learned_preferences
    def fail(*args):
        raise RuntimeError("simulated DB failure")
    monkeypatch.setattr(personalization_service, "upsert_learned_preferences", fail)
    with TestClient(app) as client:
        assert client.post("/api/agent/route-selections", json=feedback).status_code == 400
        with connect_database() as connection:
            assert connection.execute("SELECT count(*) FROM route_selection_events WHERE recommendation_id = %s", (feedback["recommendation_id"],)).fetchone()[0] == 0
        monkeypatch.setattr(personalization_service, "upsert_learned_preferences", original)
        response = client.post("/api/agent/route-selections", json=feedback)
    assert response.status_code == 200
    assert response.json()["preferences"][0]["observations"] == 1


@pytest.mark.skipif(not os.getenv("LIVE_SELECTION_PROXY_URL"), reason="optional running Compose proxy check")
def test_live_frontend_proxy_saves_and_retries_without_duplicate_learning(feedback):
    # Run inside Compose after rebuilding backend; exercise Nginx -> running API -> DB.
    with httpx.Client(base_url=os.environ["LIVE_SELECTION_PROXY_URL"], timeout=15) as client:
        for _ in range(2):
            response = client.post("/api/agent/route-selections", json=feedback)
            assert response.status_code == 200, response.text
            assert response.json()["preferences"][0]["observations"] == 1
    with connect_database() as connection:
        assert connection.execute("SELECT selected_route_type FROM route_selection_events WHERE recommendation_id = %s", (feedback["recommendation_id"],)).fetchone()[0] == "safe"
