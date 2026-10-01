import pytest

from app.repositories import place_repository


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
