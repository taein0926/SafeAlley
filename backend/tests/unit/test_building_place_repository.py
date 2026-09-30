from contextlib import contextmanager

import psycopg
import pytest

from app.repositories import building_repository as repository
from app.repositories.place_repository import PlaceAmbiguousError
from app.main import app
from app.api import places, agent
from app.schemas.agent import ParsedRouteIntent
from fastapi.testclient import TestClient


BOUNDS = (126.6, 37.4, 126.75, 37.52)


def fake_database(monkeypatch, rows):
    calls = []
    class Cursor:
        def execute(self, query, params):
            calls.append((query, params))
        def fetchall(self):
            return rows
    class Connection:
        @contextmanager
        def cursor(self, **_):
            yield Cursor()
    @contextmanager
    def connect():
        yield Connection()
    monkeypatch.setattr(repository, "connect_database", connect)
    return calls


def test_gis_query_is_bounded_parameterized_and_returns_wgs84(monkeypatch):
    row = dict(name="테스트건물", source="molit-gis-building", latitude=37.45, longitude=126.65)
    calls = fake_database(monkeypatch, [row])
    assert repository.find_building_place(" 테 스트건물 ", BOUNDS) == row
    sql, params = calls[0]
    assert params == (*BOUNDS, *(["테스트건물"] * 5), *BOUNDS)
    assert "ST_PointOnSurface" in sql and "ST_Covers" in sql
    assert "min(match_rank)" in sql and "LIMIT 2" in sql
    assert "ST_Transform(ST_PointOnSurface(geom), 4326)" in sql
    assert "FROM buildings" in sql and "INSERT" not in sql


def test_gis_query_treats_wildcards_as_literal_text(monkeypatch):
    calls = fake_database(monkeypatch, [])
    assert repository.find_building_place("%_", BOUNDS) is None
    assert calls[0][1][4] == "%_"
    assert "LIKE" not in calls[0][0]


def test_gis_never_arbitrarily_selects_a_tied_building(monkeypatch):
    fake_database(monkeypatch, [{"name": "동일건물"}, {"name": "동일건물"}])
    with pytest.raises(repository.BuildingPlaceAmbiguousError, match="전체 주소"):
        repository.find_building_place("동일건물", BOUNDS)


def test_gis_db_error_is_wrapped(monkeypatch):
    def fail():
        raise psycopg.OperationalError("offline")
    monkeypatch.setattr(repository, "connect_database", fail)
    with pytest.raises(repository.BuildingRepositoryError):
        repository.find_building_place("건물", BOUNDS)


def test_both_direct_and_ai_api_return_actionable_ambiguity(monkeypatch):
    def ambiguous(_):
        raise PlaceAmbiguousError("건물의 전체 주소로 검색해주세요.")
    monkeypatch.setattr(places, "resolve_place", ambiguous)
    monkeypatch.setattr(agent, "resolve_place", ambiguous)
    monkeypatch.setattr(agent, "parse_route_intent", lambda _: ParsedRouteIntent(origin_name="건물", destination_name="도착"))
    client = TestClient(app)
    direct = client.get("/api/places/resolve", params={"name": "건물"})
    ai = client.post("/api/agent/query", json={"query": "건물에서 도착까지"})
    for response in (direct, ai):
        assert response.status_code == 400
        assert "전체 주소" in response.json()["detail"]
