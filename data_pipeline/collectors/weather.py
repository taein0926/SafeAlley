"""Official KMA/KASI batch clients. API keys never enter the web application.

Specs: https://www.data.go.kr/data/15084084/openapi.do
       https://apihub.kma.go.kr/apiList.do?seqApi=10 (4.3)
       https://www.data.go.kr/data/15012688/openapi.do
"""
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import unquote, urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

KST = timezone(timedelta(hours=9))
KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KASI_URL = "https://apis.data.go.kr/B090041/openapi/service/RiseSetInfoService/getAreaRiseSetInfo"


def forecast_grid(latitude: float = 37.4649, longitude: float = 126.6804) -> tuple[int, int]:
    """KMA DFS LCC grid for the fixed Juan station reference (not user GPS).

    Parameters and rounding verified against KMA's convertDfsGrid(toXY):
    https://www.weather.go.kr/w/resources/js/fn.js
    """
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 < latitude < 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid forecast reference coordinates")
    rad = math.pi / 180
    re = 6371.00877 / 5
    lat1, lat2 = 30 * rad, 60 * rad
    sn = math.log(math.cos(lat1) / math.cos(lat2)) / math.log(
        math.tan(math.pi / 4 + lat2 / 2) / math.tan(math.pi / 4 + lat1 / 2)
    )
    sf = math.tan(math.pi / 4 + lat1 / 2) ** sn * math.cos(lat1) / sn
    ro = re * sf / math.tan(math.pi / 4 + 38 * rad / 2) ** sn
    ra = re * sf / math.tan(math.pi / 4 + latitude * rad / 2) ** sn
    theta = (longitude - 126) * rad
    if theta > math.pi:
        theta -= 2 * math.pi
    if theta < -math.pi:
        theta += 2 * math.pi
    theta *= sn
    nx, ny = math.floor(ra * math.sin(theta) + 43.5), math.floor(ro - ra * math.cos(theta) + 136.5)
    if not (1 <= nx <= 149 and 1 <= ny <= 253):
        raise ValueError("Reference coordinates are outside the KMA forecast grid")
    return nx, ny


class WeatherCollectionError(RuntimeError):
    pass


def read_api(url: str, parameters: dict) -> bytes:
    # Decoding once accepts both portal key forms; urlencode encodes exactly once.
    parameters = {**parameters, "serviceKey": unquote(parameters["serviceKey"])}
    try:
        with urlopen(f"{url}?{urlencode(parameters)}", timeout=20) as response:
            content = response.read(5_000_001)
        if len(content) > 5_000_000:
            raise ValueError("oversized response")
        return content
    except Exception:
        # Do not expose request URLs or upstream responses containing credentials.
        raise WeatherCollectionError("Official weather API request failed; check approval, connectivity and quota.") from None


def latest_forecast_issue(now: datetime) -> datetime:
    # Conservative 15-minute availability buffer after the eight KMA issue times.
    cutoff = now.astimezone(KST) - timedelta(minutes=15)
    hour = next((hour for hour in (23, 20, 17, 14, 11, 8, 5, 2) if hour <= cutoff.hour), None)
    if hour is None:
        cutoff -= timedelta(days=1)
        hour = 23
    return cutoff.replace(hour=hour, minute=0, second=0, microsecond=0)


def _number(value, lower: float, upper: float):
    try:
        number = float(value)
        return number if math.isfinite(number) and lower <= number <= upper else None
    except (ValueError, TypeError):
        return None


def parse_forecast(payload: dict, issue: datetime, nx: int, ny: int) -> list[dict]:
    response = payload.get("response", {})
    if str(response.get("header", {}).get("resultCode")) != "00":
        raise WeatherCollectionError("KMA did not return a successful forecast response.")
    body = response.get("body", {})
    items = (body.get("items") or {}).get("item", [])
    if not isinstance(items, list) or int(body.get("totalCount", 0)) > len(items):
        raise WeatherCollectionError("KMA forecast response is incomplete.")
    grouped = {}
    for item in items:
        if (str(item.get("baseDate")) != issue.strftime("%Y%m%d")
                or str(item.get("baseTime")) != issue.strftime("%H%M")
                or int(item.get("nx", -1)) != nx or int(item.get("ny", -1)) != ny):
            raise WeatherCollectionError("KMA forecast issue or grid does not match the request.")
        stamp = datetime.strptime(item["fcstDate"] + item["fcstTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
        grouped.setdefault(stamp, {})[item["category"]] = item["fcstValue"]
    rows = []
    for stamp, values in sorted(grouped.items()):
        sky = _number(values.get("SKY"), 1, 4)
        precipitation = _number(values.get("PTY"), 0, 4)
        rows.append({
            "forecast_at": stamp, "issued_at": issue, "nx": nx, "ny": ny,
            "temperature_c": _number(values.get("TMP"), -80, 60),
            "wind_speed_ms": _number(values.get("WSD"), 0, 150),
            "sky": int(sky) if sky in (1, 3, 4) else None,
            "precipitation_type": int(precipitation) if precipitation in (0, 1, 2, 3, 4) else None,
            "precipitation_probability": _number(values.get("POP"), 0, 100),
        })
    if not rows:
        raise WeatherCollectionError("KMA returned no forecast hours.")
    return rows


def fetch_forecast(key: str, nx: int, ny: int, now: datetime) -> list[dict]:
    issue = latest_forecast_issue(now)
    raw = read_api(KMA_URL, {
        "serviceKey": key, "dataType": "JSON", "pageNo": 1, "numOfRows": 10000,
        "base_date": issue.strftime("%Y%m%d"), "base_time": issue.strftime("%H%M"), "nx": nx, "ny": ny,
    })
    try:
        return parse_forecast(json.loads(raw), issue, nx, ny)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise WeatherCollectionError("KMA returned an invalid forecast payload.") from None


def parse_solar(raw: bytes, day: date, location: str) -> dict:
    try:
        root = ElementTree.fromstring(raw)
        if root.findtext(".//resultCode") != "00":
            raise ValueError()
        item = root.find(".//item")
        if item is None or item.findtext("locdate", "").strip() != day.strftime("%Y%m%d"):
            raise ValueError()
        if item.findtext("location", "").strip() != location:
            raise ValueError()
        def clock(tag):
            value = item.findtext(tag, "").strip()
            return datetime.strptime(value, "%H%M%S" if len(value) == 6 else "%H%M").time()
        sunrise, sunset = clock("sunrise"), clock("sunset")
        if sunrise >= sunset:
            raise ValueError()
        return {"solar_date": day, "location": location, "sunrise": sunrise, "sunset": sunset}
    except (ElementTree.ParseError, ValueError, TypeError):
        raise WeatherCollectionError("KASI returned missing or invalid daily solar times.") from None


def fetch_solar(key: str, day: date, location: str) -> dict:
    return parse_solar(read_api(KASI_URL, {
        "serviceKey": key, "locdate": day.strftime("%Y%m%d"), "location": location,
    }), day, location)
