from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


@dataclass(frozen=True)
class BuildingBoundingBox:
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float


class BuildingRepositoryError(RuntimeError):
    """Raised when building data cannot be read from PostGIS."""


def list_buildings(
    bbox: BuildingBoundingBox | None = None,
    source: str | None = None,
) -> list[dict[str, object]]:
    condition_parts: list[str] = []
    parameters: list[object] = []

    if bbox is not None:
        condition_parts.append(
            """geom && ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326),
                5179
            )"""
        )
        parameters.extend(
            [
                bbox.min_longitude,
                bbox.min_latitude,
                bbox.max_longitude,
                bbox.max_latitude,
            ]
        )
    if source is not None:
        condition_parts.append("source = %s")
        parameters.append(source)

    conditions = (
        f"WHERE {' AND '.join(condition_parts)}" if condition_parts else ""
    )
    query = f"""
        SELECT
            id,
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
            ST_AsGeoJSON(ST_Transform(geom, 4326), 7)::json AS geometry
        FROM buildings
        {conditions}
        ORDER BY id
    """

    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise BuildingRepositoryError("Failed to query buildings") from exc

