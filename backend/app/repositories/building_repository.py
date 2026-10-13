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

    def __init__(self, message: str, *, selection_context: dict[str, object] | None = None):
        super().__init__(message)
        self.selection_context = selection_context


def find_building_place(
    name: str, bounds: tuple[float, float, float, float],
) -> dict[str, object] | None:
    """Read the GIS source directly; never cache a potentially stale building copy."""
    normalized = "".join(name.split()).lower()
    if not normalized:
        return None
    query = """
        WITH normalized AS (
            SELECT id, building_name, address, main_use, source, geom,
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
        ), best AS (
            SELECT *
            FROM matches
            WHERE match_rank = (SELECT min(match_rank) FROM matches)
        ), facilities AS (
            SELECT
                min(COALESCE(NULLIF(trim(building_name), ''), address)) AS name,
                min(NULLIF(trim(address), '')) AS address,
                min(source) AS source,
                bool_and(trim(COALESCE(main_use, '')) = '공동주택') AS residential,
                ST_Collect(geom) AS geom
            FROM best
            -- MOLIT building data stores a campus or complex as several
            -- building polygons.  Equal normalized names and addresses are
            -- one real-world facility, not ambiguous places. Apartment blocks
            -- remain separate because a complex centroid can snap a route to
            -- the wrong side of a large site. Rows without an address also
            -- stay separate because proximity alone is not enough evidence.
            GROUP BY n, CASE
                WHEN trim(COALESCE(main_use, '')) = '공동주택'
                    THEN '__residential_building__' || id::text
                WHEN a <> '' THEN a
                ELSE '__building__' || id::text
            END
        ), summary AS (
            SELECT
                count(DISTINCT address) AS address_group_count,
                ST_Extent(ST_Transform(geom, 4326)) AS extent
            FROM facilities
        )
        SELECT name, 'building' AS category, address, source, residential,
            summary.address_group_count,
            ST_XMin(summary.extent) AS focus_west,
            ST_YMin(summary.extent) AS focus_south,
            ST_XMax(summary.extent) AS focus_east,
            ST_YMax(summary.extent) AS focus_north,
            ST_Y(ST_Transform(ST_Centroid(geom), 4326)) AS latitude,
            ST_X(ST_Transform(ST_Centroid(geom), 4326)) AS longitude
        FROM facilities CROSS JOIN summary
        ORDER BY name, address NULLS LAST
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
        if all(row.get("residential") is True for row in rows):
            first = rows[0]
            if first.get("address_group_count") == 1 and all(
                first.get(key) is not None
                for key in ("focus_west", "focus_south", "focus_east", "focus_north")
            ):
                focus = {
                    "west": float(first["focus_west"]),
                    "south": float(first["focus_south"]),
                    "east": float(first["focus_east"]),
                    "north": float(first["focus_north"]),
                }
                raise BuildingPlaceAmbiguousError(
                    f"'{name}' 단지 안에 건물이 여러 동 있습니다. 지도를 단지 위치로 이동했습니다. 원하는 동을 직접 선택해 주세요.",
                    selection_context={
                        "code": "building_selection_required",
                        "place_name": name,
                        "focus": focus,
                    },
                )
            raise BuildingPlaceAmbiguousError(
                f"'{name}'에 해당하는 공동주택이 여러 주소에 있습니다. 전체 주소를 입력해 주세요."
            )
        raise BuildingPlaceAmbiguousError(
            f"'{name}'에 해당하는 주소가 서로 다른 GIS 시설이 여러 곳입니다. 건물의 전체 주소로 검색해주세요."
        )
    if not rows:
        return None
    result = dict(rows[0])
    for internal_key in (
        "residential", "address_group_count", "focus_west", "focus_south",
        "focus_east", "focus_north",
    ):
        result.pop(internal_key, None)
    return result


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
