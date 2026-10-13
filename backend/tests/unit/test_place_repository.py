import pytest

from app.repositories import place_repository
from unittest.mock import MagicMock


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self, **_):
        return FakeCursor(self.rows)


def test_exact_station_wins_over_same_name_help_point(monkeypatch) -> None:
    rows = [
        {"id": 8, "name": "주안역", "category": "police", "match_rank": 0},
        {"id": 1, "name": "주안역", "category": "subway_station", "match_rank": 0},
    ]
    monkeypatch.setattr(place_repository, "connect_database", lambda: FakeConnection(rows))

    result = place_repository.find_place("주안역")

    assert result == {"id": 1, "name": "주안역", "category": "subway_station"}


def test_partial_name_with_multiple_matches_requires_clarification(monkeypatch) -> None:
    rows = [
        {"id": 1, "name": "주안역", "category": "subway_station", "match_rank": 2},
        {"id": 9, "name": "주안119안전센터", "category": "fire", "match_rank": 2},
    ]
    monkeypatch.setattr(place_repository, "connect_database", lambda: FakeConnection(rows))

    with pytest.raises(place_repository.PlaceAmbiguousError, match="여러 곳"):
        place_repository.find_place("주안")


def test_unique_place_match_is_returned(monkeypatch) -> None:
    rows = [{"id": 5, "name": "도화역", "category": "subway_station", "match_rank": 0}]
    monkeypatch.setattr(place_repository, "connect_database", lambda: FakeConnection(rows))

    assert place_repository.find_place("도화역") == {
        "id": 5,
        "name": "도화역",
        "category": "subway_station",
    }


@pytest.mark.parametrize("name,address_search", [
    ("인천대", False), ("인천대학교", False), ("서화초", False),
    ("인천대로 100", True), ("인천광역시 미추홀구 도화동 995", True),
])
def test_address_only_matches_are_disabled_for_place_names(monkeypatch, name, address_search):
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    monkeypatch.setattr(place_repository, "connect_database", lambda: connection)
    assert place_repository.find_place(name) is None
    sql, params = cursor.execute.call_args.args
    assert "OR (%s AND" in sql
    assert params[-2] is address_search


def test_ambiguous_places_return_selectable_name_address_and_coordinates(monkeypatch):
    rows = [
        {"id": 1, "name": "인천대학교", "address": "도화동 995", "source": "test", "category": "university", "latitude": 37.47, "longitude": 126.66, "match_rank": 2},
        {"id": 2, "name": "인천대학교", "address": "도화동 112-19", "source": "test", "category": "university", "latitude": 37.48, "longitude": 126.67, "match_rank": 2},
    ]
    monkeypatch.setattr(place_repository, "connect_database", lambda: FakeConnection(rows))
    with pytest.raises(place_repository.PlaceAmbiguousError) as raised:
        place_repository.find_place("인천대")
    detail = raised.value.api_detail(target="destination")
    assert detail["code"] == "place_selection_required"
    assert detail["target"] == "destination"
    assert [place["address"] for place in detail["candidates"]] == ["도화동 995", "도화동 112-19"]
    assert all("match_rank" not in place for place in detail["candidates"])
