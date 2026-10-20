from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel


class Forecast(BaseModel):
    provider: Literal["kma"] = "kma"
    forecast_at: datetime
    issued_at: datetime
    collected_at: datetime
    nx: int
    ny: int
    temperature_c: float | None
    wind_speed_ms: float | None
    sky: int | None
    precipitation_type: int | None
    precipitation_probability: float | None


class SolarTimes(BaseModel):
    provider: Literal["kasi"] = "kasi"
    solar_date: date
    location: str
    sunrise: time
    sunset: time


class WeatherResponse(BaseModel):
    date: date
    departure_time: time
    region_label: str = "미추홀구 대표 지점"
    forecast_status: Literal["available", "unavailable"]
    forecast: Forecast | None
    solar: SolarTimes | None
    theme_source: Literal["official_solar", "fallback"]
    is_night: bool
