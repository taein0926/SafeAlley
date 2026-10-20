"""Legacy juan-v1 subset collector, not the current district-wide refresh.

Current full-area updates use collectors.osm and loaders.osm_refresh.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Juan station and the Sarang hospital / Seogam school demonstration corridor.
JUAN_BBOX = (126.660, 37.450, 126.701, 37.480)  # west, south, east, north


def collect_pedestrian_tags(output: Path) -> dict:
    west, south, east, north = JUAN_BBOX
    bounds = f"{south},{west},{north},{east}"
    query = (
        '[out:json][timeout:60];('
        f'way["highway"]({bounds});node["highway"="crossing"]({bounds});'
        ');out body;>;out skel qt;'
    )
    endpoint = os.environ["OVERPASS_API_URL"].rstrip("?")
    if not endpoint.startswith("https://"):
        raise ValueError("OSM endpoint must be HTTPS")
    request = Request(endpoint + "?" + urlencode({"data": query}), headers={
        "Accept": "application/json", "User-Agent": "SafeAlley-pedestrian/1.0",
    })
    with urlopen(request, timeout=90) as response:
        document = json.load(response)
    if document.get("remark") or not document.get("elements"):
        raise ValueError("Incomplete or empty OSM response; no metadata will be loaded")
    document["safealley_scope"] = {"name": "juan-v1", "bbox": JUAN_BBOX}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return document
