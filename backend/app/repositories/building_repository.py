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


class BuildingPlaceAmbiguousError(ValueError):
    """Several equally ranked GIS buildings match a place query."""


def find_building_place(
    name: str, bounds: tuple[float, float, float, float],
) -> dict[str, object] | None:
    """Read the GIS source directly; never cache a potentially stale building copy."""
    normalized = "".join(name.split()).lower()
    if not normalized:
        return None
    query = """
        WITH normalized AS (
            SELECT building_name, address, source, geom,
                lower(regexp_replace(COALESCE(building_name, ''), '\\s+', '', 'g')) AS n,
                lower(regexp_replace(COALESCE(address, ''), '\\s+', '', 'g')) AS a
            FROM buildings
            WHERE source = 'molit-gis-building'
                AND NOT ST_IsEmpty(geom)
                AND geom && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 5179)
        ), matches AS (
            SELECT *, CASE WHEN n = %s THEN 0 WHEN a = %s THEN 1
                           WHEN strpos(n, %s) > 0 THEN 2 ELSE 3 END AS match_rank
            FROM normalized
            WHERE (strpos(n, %s) > 0 OR strpos(a, %s) > 0)
                AND ST_Covers(
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326),
                    ST_Transform(ST_PointOnSurface(geom), 4326)
                )
        )
        SELECT COALESCE(NULLIF(trim(building_name), ''), address) AS name,
            'building' AS category, address, source,
            ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)) AS latitude,
            ST_X(ST_Transform(ST_PointOnSurface(geom), 4326)) AS longitude
        FROM matches
        WHERE match_rank = (SELECT min(match_rank) FROM matches)
        LIMIT 2
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, (*bounds, *([normalized] * 5), *bounds))
                rows = cursor.fetchall()
    except psycopg.Error as exc:
        raise BuildingRepositoryError("GIS building name search is unavailable") from exc
    if len(rows) > 1:
        raise BuildingPlaceAmbiguousError(
            f"'{name}'에 해당하는 GIS 건물이 여러 곳입니다. 건물의 전체 주소로 검색해주세요."
        )
    return dict(rows[0]) if rows else None


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
