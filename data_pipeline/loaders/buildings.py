import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection


class BuildingLoadError(RuntimeError):
    """Raised when processed building GeoJSON is invalid or cannot be loaded."""


UPSERT_BUILDING_SQL = """
    WITH source_geometry AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom
    ),
    normalized AS (
        SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
        FROM source_geometry
    ),
    transformed AS (
        SELECT ST_Transform(geom, 5179) AS geom
        FROM normalized
        WHERE NOT ST_IsEmpty(geom)
    )
    INSERT INTO buildings (
        source,
        building_id,
        building_name,
        address,
        main_use,
        building_area,
        total_floor_area,
        height_m,
        floors,
        source_updated_at,
        geom,
        properties
    )
    SELECT
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        transformed.geom,
        %s
    FROM transformed
    ON CONFLICT (source, building_id) DO UPDATE SET
        building_name = EXCLUDED.building_name,
        address = EXCLUDED.address,
        main_use = EXCLUDED.main_use,
        building_area = EXCLUDED.building_area,
        total_floor_area = EXCLUDED.total_floor_area,
        height_m = EXCLUDED.height_m,
        floors = EXCLUDED.floors,
        source_updated_at = EXCLUDED.source_updated_at,
        geom = EXCLUDED.geom,
        properties = EXCLUDED.properties,
        updated_at = NOW()
"""


def read_building_features(path: Path) -> list[dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildingLoadError(f"Cannot read processed buildings: {path}") from exc

    if document.get("type") != "FeatureCollection":
        raise BuildingLoadError("Processed buildings must be a GeoJSON FeatureCollection")
    if document.get("metadata", {}).get("crs") != "EPSG:4326":
        raise BuildingLoadError("Processed building GeoJSON must use EPSG:4326")
    features = document.get("features")
    if not isinstance(features, list):
        raise BuildingLoadError("Processed buildings require a features array")
    return features


def load_buildings(path: Path, replace_source: str | None = None) -> int:
    features = read_building_features(path)
    loaded_count = 0

    with database_connection() as connection:
        with connection.cursor() as cursor:
            if replace_source is not None:
                cursor.execute("DELETE FROM buildings WHERE source = %s", (replace_source,))
            for feature in features:
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                geometry_type = geometry.get("type")
                if geometry_type not in {"Polygon", "MultiPolygon"}:
                    raise BuildingLoadError(
                        f"Building {properties.get('building_id')} has invalid geometry: "
                        f"{geometry_type}"
                    )
                source = str(properties.get("source") or "").strip()
                building_id = str(properties.get("building_id") or "").strip()
                if not source or not building_id:
                    raise BuildingLoadError("Every building requires source and building_id")
                cursor.execute(
                    UPSERT_BUILDING_SQL,
                    (
                        json.dumps(geometry),
                        source,
                        building_id,
                        properties.get("building_name"),
                        properties.get("address"),
                        properties.get("main_use"),
                        properties.get("building_area"),
                        properties.get("total_floor_area"),
                        properties.get("height_m"),
                        properties.get("floors"),
                        properties.get("source_updated_at"),
                        Jsonb(properties),
                    ),
                )
                if cursor.rowcount != 1:
                    raise BuildingLoadError(
                        f"Building {building_id} produced an empty geometry"
                    )
                loaded_count += 1

    return loaded_count

