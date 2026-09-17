from pathlib import Path

from psycopg.types.json import Jsonb

from loaders.postgis import database_connection
from preprocess.help_points import validate_help_points


def load_help_points(
    path: Path,
    *,
    replace_source: str = "ai-ready-help-points",
) -> dict[str, object]:
    rows, stats = validate_help_points(path)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM help_points WHERE source = %s", (replace_source,))
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO help_points (
                        source, external_id, name, category, subtype, address,
                        phone, emergency_phone, coordinate_quality,
                        coordinate_status, coordinate_source, source_org,
                        source_dataset, reference_date, geom, properties
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s,
                        ST_Transform(
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179
                        ),
                        %s
                    )
                    """,
                    (
                        replace_source,
                        row["external_id"], row["name"], row["category"],
                        row["subtype"], row["address"], row["phone"],
                        row["emergency_phone"], row["coordinate_quality"],
                        row["coordinate_status"], row["coordinate_source"],
                        row["source_org"], row["source_dataset"],
                        row["reference_date"], row["longitude"], row["latitude"],
                        Jsonb(row["properties"]),
                    ),
                )
    return stats
