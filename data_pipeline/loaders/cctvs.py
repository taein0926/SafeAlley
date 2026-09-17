import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection


class CctvLoadError(RuntimeError):
    """Raised when normalized CCTV records cannot be loaded."""


def load_cctvs(path: Path, *, replace_source: str) -> int:
    try:
        records: list[dict[str, Any]] = json.loads(
            path.read_text(encoding="utf-8")
        )["records"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CctvLoadError(f"Cannot read processed CCTV JSON: {path}") from exc

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM cctvs WHERE source = %s", (replace_source,))
            for row in records:
                cursor.execute(
                    """
                    INSERT INTO cctvs (
                        source, source_id, management_agency, road_address,
                        parcel_address, purpose, camera_count, camera_pixels,
                        direction_info, retention_days, installed_at,
                        agency_phone, longitude, latitude, geom,
                        data_reference_date, is_safety_cctv, properties
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s,
                        CASE WHEN %s::double precision IS NULL
                                  OR %s::double precision IS NULL
                            THEN NULL
                            ELSE ST_Transform(
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179
                            )
                        END,
                        %s, %s, %s
                    )
                    """,
                    (
                        row["source"], row["source_id"], row["management_agency"],
                        row["road_address"], row["parcel_address"], row["purpose"],
                        row["camera_count"], row["camera_pixels"],
                        row["direction_info"], row["retention_days"],
                        row["installed_at"], row["agency_phone"], row["longitude"],
                        row["latitude"], row["longitude"], row["latitude"],
                        row["longitude"], row["latitude"], row["data_reference_date"],
                        row["is_safety_cctv"], Jsonb(row["properties"]),
                    ),
                )
    return len(records)
