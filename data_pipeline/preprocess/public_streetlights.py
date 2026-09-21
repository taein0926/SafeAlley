"""Extract documented streetlight POIs from the official Incheon road dataset."""

import json
from pathlib import Path

import fiona
from pyproj import Transformer

from preprocess.public_crosswalks import SOURCE_DATASET, SOURCE_URL


SOURCE = "incheon-road-poi-2022"


def preprocess_incheon_streetlights(source_zip: Path, output_path: Path) -> dict[str, int]:
    features = []
    seen_ids = set()
    with fiona.open(f"zip://{source_zip.resolve().as_posix()}") as source:
        if not source.crs:
            raise ValueError("Official streetlight SHP has no declared CRS")
        to_wgs84 = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        for feature in source:
            properties = dict(feature["properties"])
            if properties.get("시군구명") != "미추홀구" or properties.get("시설물명칭") != "가로등":
                continue
            facility_id = properties.get("시설물ID")
            geometry = feature.get("geometry")
            if not facility_id or facility_id in seen_ids or not geometry or geometry["type"] != "Point":
                continue
            longitude, latitude = to_wgs84.transform(*geometry["coordinates"][:2])
            if not (126.55 <= longitude <= 126.8 and 37.35 <= latitude <= 37.55):
                continue
            seen_ids.add(facility_id)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": {
                    "source": SOURCE,
                    "source_id": facility_id,
                    "pole_name": None,
                    "cabinet_name": None,
                    "label_no": None,
                    "longitude": longitude,
                    "latitude": latitude,
                    "source_dataset": SOURCE_DATASET,
                    "source_url": SOURCE_URL,
                    "reference_date": "2022-10-31",
                    "license": "이용허락범위 제한 없음",
                    "coverage_warning": "Only roads of two or more lanes; operation status is unknown",
                },
            })
    if not features:
        raise ValueError("No valid Michuhol-gu streetlight POIs found")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {
            "crs": "EPSG:4326",
            "source": SOURCE_DATASET,
            "source_url": SOURCE_URL,
            "reference_date": "2022-10-31",
            "license": "이용허락범위 제한 없음",
            "limitation": "Only roads of two or more lanes; operation and illuminance unverified",
        },
        "features": features,
    }, ensure_ascii=False), encoding="utf-8")
    return {"streetlights": len(features)}
