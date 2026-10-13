import re

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


class PlaceNotFoundError(RuntimeError):
    """Raised when a place cannot be resolved inside the project area."""


class PlaceAmbiguousError(ValueError):
    """The caller must supply a more specific location before routing."""

    def __init__(self, message: str, *, selection_context: dict[str, object] | None = None):
        super().__init__(message)
        self.selection_context = selection_context

    def api_detail(self, *, target: str | None = None) -> str | dict[str, object]:
        if self.selection_context is None:
            return str(self)
        detail = {"message": str(self), **self.selection_context}
        if target is not None:
            detail["target"] = target
        return detail


class PlaceRepositoryError(RuntimeError):
    """Raised when the local place index cannot be queried or updated."""


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def find_place(name: str) -> dict[str, object] | None:
    """Find the best local name, alias, or address match."""

    normalized = _normalized(name)
    query = """
        SELECT
            id, name, category, address, source,
            ST_Y(ST_Transform(geom, 4326)) AS latitude,
            ST_X(ST_Transform(geom, 4326)) AS longitude,
            CASE
                WHEN lower(regexp_replace(name, '\\s+', '', 'g')) = %s THEN 0
                WHEN EXISTS (
                    SELECT 1 FROM unnest(aliases) AS alias
                    WHERE lower(regexp_replace(alias, '\\s+', '', 'g')) = %s
                ) THEN 1
                WHEN lower(regexp_replace(name, '\\s+', '', 'g')) LIKE %s THEN 2
                WHEN EXISTS (
                    SELECT 1 FROM unnest(aliases) AS alias
                    WHERE lower(regexp_replace(alias, '\\s+', '', 'g')) LIKE %s
                ) THEN 3
                ELSE 4
            END AS match_rank
        FROM places
        WHERE
            lower(regexp_replace(name, '\\s+', '', 'g')) = %s
            OR EXISTS (
                SELECT 1 FROM unnest(aliases) AS alias
                WHERE lower(regexp_replace(alias, '\\s+', '', 'g')) = %s
            )
            OR lower(regexp_replace(name, '\\s+', '', 'g')) LIKE %s
            OR EXISTS (
                SELECT 1 FROM unnest(aliases) AS alias
                WHERE lower(regexp_replace(alias, '\\s+', '', 'g')) LIKE %s
            )
            OR lower(regexp_replace(COALESCE(address, ''), '\\s+', '', 'g')) LIKE %s
        ORDER BY match_rank, length(name), name, id
        LIMIT 10
    """
    partial = f"%{normalized}%"
    parameters = (
        normalized,
        normalized,
        partial,
        partial,
        normalized,
        normalized,
        partial,
        partial,
        partial,
    )
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                rows = cursor.fetchall()
    except psycopg.Error as exc:
        raise PlaceRepositoryError("Place index is unavailable") from exc
    if not rows:
        return None
    best_rank = rows[0]["match_rank"]
    tied = [row for row in rows if row["match_rank"] == best_rank]
    # A station can share its display name with a nearby police/help point.
    if normalized.endswith("역"):
        exact_stations = [
            row for row in tied
            if row["category"] == "subway_station"
            and _normalized(row["name"]) == normalized
        ]
        if len(exact_stations) == 1:
            return {key: value for key, value in exact_stations[0].items() if key != "match_rank"}
    if len(tied) > 1:
        raise PlaceAmbiguousError(
            f"'{name}'에 해당하는 장소가 여러 곳입니다. 장소명이나 주소를 더 구체적으로 입력해 주세요."
        )
    return {key: value for key, value in rows[0].items() if key != "match_rank"}


def get_osm_road_viewbox() -> tuple[float, float, float, float]:
    """Return min lon/lat and max lon/lat for the loaded OSM routing area."""

    query = """
        SELECT
            ST_XMin(extent) AS min_lon,
            ST_YMin(extent) AS min_lat,
            ST_XMax(extent) AS max_lon,
            ST_YMax(extent) AS max_lat
        FROM (
            SELECT ST_Extent(ST_Transform(geom, 4326)) AS extent
            FROM road_segments
            WHERE source = 'osm'
        ) bounds
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
    except psycopg.Error as exc:
        raise PlaceRepositoryError("OSM routing bounds are unavailable") from exc
    if row is None or any(
        row[key] is None for key in ("min_lon", "min_lat", "max_lon", "max_lat")
    ):
        raise PlaceRepositoryError("OSM routing bounds are unavailable")
    return tuple(
        float(row[key]) for key in ("min_lon", "min_lat", "max_lon", "max_lat")
    )


def cache_geocoded_place(place: dict[str, object], query_name: str) -> None:
    """Cache one bounded geocoder result in the existing places table."""

    query = """
        INSERT INTO places (
            source, source_id, name, aliases, category, address, geom
        )
        VALUES (
            %s, %s, %s, ARRAY[%s]::text[], %s, %s,
            ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179)
        )
        ON CONFLICT (source, source_id) DO UPDATE SET
            name = EXCLUDED.name,
            aliases = ARRAY(
                SELECT DISTINCT alias
                FROM unnest(places.aliases || EXCLUDED.aliases) AS alias
                WHERE alias <> ''
            ),
            category = EXCLUDED.category,
            address = EXCLUDED.address,
            geom = EXCLUDED.geom
    """
    try:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        place["source"],
                        place["source_id"],
                        place["name"],
                        query_name.strip(),
                        place.get("category"),
                        place.get("address"),
                        place["longitude"],
                        place["latitude"],
                    ),
                )
    except psycopg.Error as exc:
        raise PlaceRepositoryError("Geocoded place could not be cached") from exc
