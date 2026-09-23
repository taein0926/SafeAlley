from datetime import datetime, date, time
import json
import os
from uuid import uuid4

import pytest
from collectors import weather

ISSUE = datetime(2026, 9, 23, 14, tzinfo=weather.KST)


def test_official_grid_conversion_for_juan_and_projection_origin():
    assert weather.forecast_grid() == (55, 124)
    assert weather.forecast_grid(38, 126) == (43, 136)
    with pytest.raises(ValueError):
        weather.forecast_grid(float("nan"), 126)
    with pytest.raises(ValueError):
        weather.forecast_grid(0, 0)


def payload(values):
    items = [{"baseDate": "20260923", "baseTime": "1400", "fcstDate": "20260923",
              "fcstTime": "1500", "nx": 55, "ny": 124, "category": key, "fcstValue": value}
             for key, value in values.items()]
    return {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": items}, "totalCount": len(items)}}}


@pytest.mark.parametrize("hour,minute,day,expected", [(0, 5, 22, 23), (2, 14, 22, 23), (2, 15, 23, 2), (14, 10, 23, 11), (14, 15, 23, 14)])
def test_issue_date_and_release_buffer(hour, minute, day, expected):
    issue = weather.latest_forecast_issue(ISSUE.replace(hour=hour, minute=minute))
    assert (issue.day, issue.hour, issue.minute) == (day, expected, 0)


def test_forecast_fields_units_and_missing_values():
    row = weather.parse_forecast(payload({"TMP": "28", "WSD": "3", "PTY": "1", "POP": "80", "SKY": "4"}), ISSUE, 55, 124)[0]
    assert row["temperature_c"] == 28 and row["wind_speed_ms"] == 3
    assert row["precipitation_type"] == 1 and row["precipitation_probability"] == 80
    row = weather.parse_forecast(payload({"TMP": "-999", "WSD": "NaN", "SKY": "2"}), ISSUE, 55, 124)[0]
    assert row["temperature_c"] is None and row["wind_speed_ms"] is None and row["sky"] is None
    assert row["precipitation_type"] is None


def test_wrong_grid_and_pagination_are_rejected():
    data = payload({"TMP": "28"})
    with pytest.raises(weather.WeatherCollectionError):
        weather.parse_forecast(data, ISSUE, 56, 124)
    data["response"]["body"]["totalCount"] = 2
    with pytest.raises(weather.WeatherCollectionError):
        weather.parse_forecast(data, ISSUE, 55, 124)


def test_api_errors_are_not_zero_temperature():
    with pytest.raises(weather.WeatherCollectionError):
        weather.parse_forecast({"response": {"header": {"resultCode": "30"}}}, ISSUE, 55, 124)


def solar_xml(sunrise="0620", sunset="183000", location="인천", day="20260923"):
    return f"<response><header><resultCode>00</resultCode></header><body><items><item><locdate>{day}</locdate><location>{location}</location><sunrise>{sunrise}</sunrise><sunset>{sunset}</sunset></item></items></body></response>".encode()


def test_kasi_response_and_minute_second_precision():
    row = weather.parse_solar(solar_xml(), date(2026, 9, 23), "인천")
    assert row["sunrise"] == time(6, 20) and row["sunset"] == time(18, 30)


@pytest.mark.parametrize("changes", [{"sunrise": "----"}, {"sunset": "0600"}, {"day": "20260922"}, {"location": "서울"}])
def test_solar_wrong_date_location_or_missing_time_rejected(changes):
    with pytest.raises(weather.WeatherCollectionError):
        weather.parse_solar(solar_xml(**changes), date(2026, 9, 23), "인천")


def test_http_error_does_not_leak_key(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("url?serviceKey=secret-test-key")
    monkeypatch.setattr(weather, "urlopen", fail)
    with pytest.raises(weather.WeatherCollectionError) as exc:
        weather.read_api(weather.KMA_URL, {"serviceKey": "secret-test-key"})
    assert "secret-test-key" not in str(exc.value)


def test_key_is_urlencoded_once_and_timeout_is_bounded(monkeypatch):
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, *_): return b"{}"
    def open_fake(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(weather, "urlopen", open_fake)
    weather.read_api(weather.KMA_URL, {"serviceKey": "test%2Bkey%3D"})
    assert "test%2Bkey%3D" in calls[0][0] and "%252B" not in calls[0][0]
    assert calls[0][1]["timeout"] == 20


@pytest.mark.skipif(not os.environ.get("DB_HOST"), reason="Configured test DB required")
def test_cache_upsert_keeps_newest_issue_and_preserves_other_regions():
    from loaders.weather import save_forecasts, save_solar
    from loaders.postgis import database_connection
    region = "weather-test-" + uuid4().hex
    row = weather.parse_forecast(payload({"TMP": "28", "WSD": "3"}), ISSUE, 55, 124)[0]
    try:
        save_forecasts([row], region)
        save_forecasts([{**row, "issued_at": ISSUE.replace(hour=11), "temperature_c": 22}], region)
        save_solar(weather.parse_solar(solar_xml(), ISSUE.date(), "인천"), region)
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT temperature_c, wind_speed_ms FROM weather_forecasts WHERE region = %s", (region,))
            assert cursor.fetchall() == [(28, 3)]
            cursor.execute("SELECT sunrise, sunset FROM solar_times WHERE region = %s", (region,))
            assert cursor.fetchall() == [(time(6, 20), time(18, 30))]
    finally:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM weather_forecasts WHERE region = %s", (region,))
            cursor.execute("DELETE FROM solar_times WHERE region = %s", (region,))
