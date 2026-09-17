import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OsmCollectionError(RuntimeError):
    """Raised when OpenStreetMap data cannot be collected or validated."""


def build_overpass_query(area_name: str, admin_level: str) -> str:
    escaped_name = area_name.replace("\\", "\\\\").replace('"', '\\"')
    escaped_level = admin_level.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
[out:json][timeout:180];
area["boundary"="administrative"]["admin_level"="{escaped_level}"]["name"="{escaped_name}"]->.searchArea;
way["highway"](area.searchArea);
out body;
>;
out skel qt;
""".strip()


def collect_osm_roads(output_path: Path) -> int:
    endpoint = os.environ["OVERPASS_API_URL"].strip()
    area_name = os.getenv("OSM_AREA_NAME", "미추홀구").strip()
    admin_level = os.getenv("OSM_AREA_ADMIN_LEVEL", "6").strip()
    timeout_seconds = int(os.getenv("OVERPASS_TIMEOUT_SECONDS", "240"))
    user_agent = os.getenv(
        "OSM_USER_AGENT",
        "SafeAlley-MVP/0.1 (local development)",
    ).strip()
    if not endpoint.startswith("https://"):
        raise OsmCollectionError("OVERPASS_API_URL must be an HTTPS endpoint")
    if not area_name or not admin_level:
        raise OsmCollectionError("OSM area name and admin level are required")

    query = build_overpass_query(area_name, admin_level)
    request = Request(
        endpoint,
        data=urlencode({"data": query}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": user_agent,
        },
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                document = json.load(response)
            break
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    else:
        raise OsmCollectionError(
            "Overpass request failed after 3 attempts; retry later or set a different "
            "verified OVERPASS_API_URL"
        ) from last_error

    elements = document.get("elements")
    if not isinstance(elements, list) or not elements:
        raise OsmCollectionError(
            f"Overpass returned no elements for {area_name!r} at admin_level {admin_level}"
        )
    if not any(element.get("type") == "way" for element in elements):
        raise OsmCollectionError("Overpass response contains no highway ways")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata_path = output_path.with_suffix(".meta.json")
    metadata_path.write_text(
        json.dumps(
            {
                "source": "OpenStreetMap",
                "license": "ODbL-1.0",
                "area_name": area_name,
                "admin_level": admin_level,
                "overpass_api_url": endpoint,
                "query": query,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return len(elements)
