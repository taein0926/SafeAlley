from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


class WeatherReadError(RuntimeError):
    pass


def read_weather(hour: datetime, day: date) -> tuple[dict | None, dict | None]:
    """Read a fixed Michuhol reference area; no user's GPS is collected."""
    try:
        with connect_database() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT provider, forecast_at, issued_at, collected_at, nx, ny, temperature_c,
                    wind_speed_ms, sky, precipitation_type, precipitation_probability
                FROM weather_forecasts WHERE region = 'michuhol' AND forecast_at = %s AND provider = 'kma'
            """, (hour,))
            forecast = cursor.fetchone()
            cursor.execute("""
                SELECT provider, solar_date, location, sunrise, sunset FROM solar_times
                WHERE region = 'michuhol' AND solar_date = %s AND provider = 'kasi'
            """, (day,))
            return forecast, cursor.fetchone()
    except psycopg.Error:
        raise WeatherReadError("Weather cache is unavailable") from None
