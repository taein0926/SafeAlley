import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection


class StreetlightLoadError(RuntimeError):
    """Raised when processed streetlight data cannot be loaded."""


INSERT_STREETLIGHT_SQL = """
    WITH point AS (
        SELECT ST_Transform(
            ST_SetSRID(ST_MakePoint(%s, %s), 4326),
            5179
        ) AS geom
    )
    INSERT INTO streetlights (
        source,
        source_id,
        pole_name,
        cabinet_name,
        label_no,
        longitude,
        latitude,
        geom,
        properties
    )
    SELECT %s, %s, %s, %s, %s, %s, %s, point.geom, %s
    FROM point
    ON CONFLICT (source, source_id) DO UPDATE SET
        pole_name = EXCLUDED.pole_name,
        cabinet_name = EXCLUDED.cabinet_name,
        label_no = EXCLUDED.label_no,
        longitude = EXCLUDED.longitude,
        latitude = EXCLUDED.latitude,
        geom = EXCLUDED.geom,
        properties = EXCLUDED.properties,
        matched_road_id = NULL,
        matched_road_distance_m = NULL,
        updated_at = NOW()
"""


def _read_features(path: Path) -> list[dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StreetlightLoadError(f"Cannot read processed streetlights: {path}") from exc
    if document.get("type") != "FeatureCollection":
        raise StreetlightLoadError("Streetlights must be a GeoJSON FeatureCollection")
    if document.get("metadata", {}).get("crs") != "EPSG:4326":
        raise StreetlightLoadError("Streetlight GeoJSON must use EPSG:4326")
    features = document.get("features")
    if not isinstance(features, list):
        raise StreetlightLoadError("Streetlight GeoJSON requires a features array")
    return features


def load_streetlights(path: Path, *, replace_source: str) -> int:
    features = _read_features(path)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM streetlights WHERE source = %s",
                (replace_source,),
            )
            for feature in features:
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                if geometry.get("type") != "Point":
                    raise StreetlightLoadError("Every streetlight geometry must be Point")
                coordinates = geometry.get("coordinates") or []
                if len(coordinates) < 2:
                    raise StreetlightLoadError("Streetlight Point requires two coordinates")
                longitude = float(coordinates[0])
                latitude = float(coordinates[1])
                cursor.execute(
                    INSERT_STREETLIGHT_SQL,
                    (
                        longitude,
                        latitude,
                        properties["source"],
                        properties["source_id"],
                        properties.get("pole_name"),
                        properties.get("cabinet_name"),
                        properties.get("label_no"),
                        longitude,
                        latitude,
                        Jsonb(properties),
                    ),
                )
    return len(features)
