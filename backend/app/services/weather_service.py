from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from app.repositories.weather_repository import WeatherReadError, read_weather
from app.schemas.weather import WeatherResponse

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class RouteTimeContext:
    departure_time: time
    is_night: bool
    theme_source: str


def resolve_route_time(departure_time: time | None, *, now: datetime | None = None) -> RouteTimeContext:
    """Use the same daily solar cache as the map, once per route search."""
    now = (now or datetime.now(KST)).astimezone(KST)
    departure = (departure_time or now.time()).replace(tzinfo=None, microsecond=0)
    try:
        weather = get_weather(departure, now=now)
        return RouteTimeContext(departure, weather.is_night, weather.theme_source)
    except WeatherReadError:
        # A missing weather cache must not prevent routing; match the map fallback.
        return RouteTimeContext(departure, departure < time(6) or departure >= time(20), "fallback")


def get_weather(departure_time: time | None, *, now: datetime | None = None) -> WeatherResponse:
    now = (now or datetime.now(KST)).astimezone(KST)
    departure = (departure_time or now.time()).replace(tzinfo=None, microsecond=0)
    hour = datetime.combine(now.date(), departure, KST).replace(minute=0, second=0)
    forecast, solar = read_weather(hour, now.date())
    status = "unavailable"
    if forecast:
        reference_time = forecast["issued_at"]
        # The repository selects today's requested forecast hour. Publication
        # age alone must not hide that hour's forecast; reject invalid future issues.
        status = "available" if reference_time is not None and reference_time <= now else "unavailable"
    if solar and solar["solar_date"] == now.date() and solar["sunrise"] < solar["sunset"]:
        night = departure < solar["sunrise"] or departure >= solar["sunset"]
    else:
        solar = None
        night = departure < time(6) or departure >= time(20)
    return WeatherResponse(
        date=now.date(), departure_time=departure, forecast_status=status,
        forecast=forecast if status == "available" else None, solar=solar,
        theme_source="official_solar" if solar else "fallback", is_night=night,
    )
