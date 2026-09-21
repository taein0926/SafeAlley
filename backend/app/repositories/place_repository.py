import re

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


class PlaceNotFoundError(RuntimeError):
    """Raised when a natural-language place cannot be resolved locally."""


class PlaceRepositoryError(RuntimeError):
    """Raised when the local place index cannot be queried."""


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def resolve_place(name: str) -> dict[str, object]:
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
                ELSE 2
            END AS match_rank
        FROM places
        WHERE
            lower(regexp_replace(name, '\\s+', '', 'g')) = %s
            OR EXISTS (
                SELECT 1 FROM unnest(aliases) AS alias
                WHERE lower(regexp_replace(alias, '\\s+', '', 'g')) = %s
            )
            OR name ILIKE %s
        ORDER BY match_rank, name, id
        LIMIT 1
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    query,
                    (normalized, normalized, normalized, normalized, f"%{name.strip()}%"),
                )
                row = cursor.fetchone()
    except psycopg.Error as exc:
        raise PlaceRepositoryError("Place index is unavailable") from exc
    if row is None:
        raise PlaceNotFoundError(
            f"'{name}' 장소를 DB에서 찾지 못했습니다. 등록된 장소명을 사용해 주세요."
        )
    return dict(row)
