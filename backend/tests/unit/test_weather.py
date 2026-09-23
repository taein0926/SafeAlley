from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import weather_service
from app.services.weather_service import KST

NOW = datetime(2026, 9, 23, 14, 30, tzinfo=KST)


def forecast(**changes):
    return {"forecast_at": NOW.replace(minute=0), "issued_at": NOW - timedelta(hours=1),
            "collected_at": NOW, "nx": 55, "ny": 124, "temperature_c": 28,
            "wind_speed_ms": 3, "sky": 1, "precipitation_type": 0,
            "precipitation_probability": 0, **changes}


def solar(**changes):
    # Test fixture only, not an official daily observation.
    return {"solar_date": NOW.date(), "location": "인천", "sunrise": time(6, 20),
            "sunset": time(18, 30), **changes}


@pytest.mark.parametrize("departure,night", [(time(6, 19), True), (time(6, 20), False),
                                                  (time(18, 29), False), (time(18, 30), True)])
def test_theme_uses_sunrise_sunset_not_fixed_hours(monkeypatch, departure, night):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (forecast(), solar()))
    result = weather_service.get_weather(departure, now=NOW)
    assert result.is_night is night
    assert result.theme_source == "official_solar"


def test_missing_data_does_not_invent_weather(monkeypatch):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (None, None))
    result = weather_service.get_weather(time(22), now=NOW)
    assert result.forecast is None and result.solar is None
    assert result.forecast_status == "unavailable" and result.theme_source == "fallback"
    assert result.is_night


@pytest.mark.parametrize("offset", [-7, 1])
def test_stale_or_future_issue_is_not_displayed(monkeypatch, offset):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (forecast(issued_at=NOW + timedelta(hours=offset)), solar()))
    result = weather_service.get_weather(time(14), now=NOW)
    assert result.forecast_status == "stale" and result.forecast is None
    assert result.solar is not None


def test_korea_date_rollover_and_exact_hour(monkeypatch):
    calls = []
    monkeypatch.setattr(weather_service, "read_weather", lambda *args: (calls.append(args) or None, solar()))
    now = NOW.replace(hour=0, minute=3)
    result = weather_service.get_weather(time(0, 40), now=now)
    assert calls[0][0].hour == 0 and calls[0][0].minute == 0
    assert result.date == now.date()


def test_yesterday_solar_is_not_reused(monkeypatch):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (None, solar(solar_date=NOW.date() - timedelta(days=1))))
    assert weather_service.get_weather(time(19), now=NOW).theme_source == "fallback"


@pytest.mark.parametrize("value", ["25:00", "bad", "15:00Z"])
def test_invalid_departure_query_rejected(value):
    assert TestClient(app).get("/api/weather", params={"departure_time": value}).status_code == 422


def test_api_serves_cache_without_external_requests(monkeypatch):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (None, None))
    response = TestClient(app).get("/api/weather?departure_time=22:00")
    assert response.status_code == 200
    assert response.json()["forecast"] is None and response.json()["is_night"]


def test_api_uses_only_official_provider_types(monkeypatch):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (
        forecast(provider="kma"), solar(provider="kasi"),
    ))
    result = weather_service.get_weather(time(19), now=NOW)
    assert result.forecast_status == "available" and result.forecast.provider == "kma"
    assert result.solar.provider == "kasi"
    assert result.theme_source == "official_solar" and result.is_night


def test_recollecting_old_forecast_does_not_refresh_its_issue_age(monkeypatch):
    monkeypatch.setattr(weather_service, "read_weather", lambda *_: (
        forecast(issued_at=NOW - timedelta(hours=7), collected_at=NOW), solar(),
    ))
    result = weather_service.get_weather(time(14), now=NOW)
    assert result.forecast_status == "stale" and result.forecast is None
    assert result.solar.provider == "kasi" and not result.is_night
