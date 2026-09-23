"""Idempotent cache upserts; no replacement or deletion of project datasets."""
from loaders.postgis import database_connection


def save_forecasts(rows: list[dict], region: str = "michuhol") -> int:
    with database_connection() as connection, connection.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO weather_forecasts (region, provider, forecast_at, issued_at, nx, ny,
                temperature_c, wind_speed_ms, sky, precipitation_type, precipitation_probability)
            VALUES (%(region)s, 'kma', %(forecast_at)s, %(issued_at)s, %(nx)s, %(ny)s,
                %(temperature_c)s, %(wind_speed_ms)s, %(sky)s, %(precipitation_type)s, %(precipitation_probability)s)
            ON CONFLICT (region, forecast_at) DO UPDATE SET
                provider = EXCLUDED.provider,
                issued_at = EXCLUDED.issued_at, collected_at = now(), nx = EXCLUDED.nx, ny = EXCLUDED.ny,
                temperature_c = EXCLUDED.temperature_c, wind_speed_ms = EXCLUDED.wind_speed_ms,
                sky = EXCLUDED.sky, precipitation_type = EXCLUDED.precipitation_type,
                precipitation_probability = EXCLUDED.precipitation_probability
            WHERE EXCLUDED.provider <> weather_forecasts.provider
                OR weather_forecasts.issued_at IS NULL
                OR EXCLUDED.issued_at >= weather_forecasts.issued_at
        """, [{**row, "region": region} for row in rows])
    return len(rows)


def save_solar(row: dict, region: str = "michuhol") -> None:
    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO solar_times (region, provider, solar_date, location, sunrise, sunset)
            VALUES (%(region)s, 'kasi', %(solar_date)s, %(location)s, %(sunrise)s, %(sunset)s)
            ON CONFLICT (region, solar_date) DO UPDATE SET location = EXCLUDED.location,
                provider = EXCLUDED.provider,
                sunrise = EXCLUDED.sunrise, sunset = EXCLUDED.sunset, collected_at = now()
        """, {**row, "region": region})
