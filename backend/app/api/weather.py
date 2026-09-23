from datetime import time

from fastapi import APIRouter, HTTPException

from app.repositories.weather_repository import WeatherReadError
from app.schemas.weather import WeatherResponse
from app.services.weather_service import get_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("", response_model=WeatherResponse)
def weather(departure_time: time | None = None) -> WeatherResponse:
    if departure_time is not None and departure_time.tzinfo is not None:
        raise HTTPException(422, "Use local Korea time without a timezone suffix")
    try:
        return get_weather(departure_time)
    except WeatherReadError:
        raise HTTPException(503, "Weather data is temporarily unavailable") from None
