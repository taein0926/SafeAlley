"""Extract official Incheon crosswalk POIs without conflating nearby roads."""

import json
from pathlib import Path

import fiona
from pyproj import Transformer


SOURCE_URL = "https://www.data.go.kr/data/15111545/fileData.do"
SOURCE_DATASET = "인천광역시_도로시설물 3차원 POI 데이터_20221031"


def preprocess_incheon_crosswalks(source_zip: Path, output_path: Path) -> dict[str, int]:
    features = []
    seen_ids = set()
    with fiona.open(f"zip://{source_zip.resolve().as_posix()}") as source:
        if not source.crs:
            raise ValueError("Official crosswalk SHP has no declared CRS")
        to_wgs84 = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        for feature in source:
            properties = dict(feature["properties"])
            if properties.get("시군구명") != "미추홀구" or properties.get("시설물명칭") != "횡단보도":
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
                    "source_id": facility_id,
                    "name": "횡단보도",
                    "district": "미추홀구",
                    "reference_date": "2022-10-31",
                    "source_dataset": SOURCE_DATASET,
                    "source_url": SOURCE_URL,
                    "license": "이용허락범위 제한 없음",
                },
            })
    if not features:
        raise ValueError("No valid Michuhol-gu crosswalk POIs found")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {
            "source": SOURCE_DATASET,
            "source_url": SOURCE_URL,
            "reference_date": "2022-10-31",
            "license": "이용허락범위 제한 없음",
            "limitation": "Only roads of two or more lanes; POIs do not prove a route crosses here",
        },
        "features": features,
    }, ensure_ascii=False), encoding="utf-8")
    return {"crosswalks": len(features)}
