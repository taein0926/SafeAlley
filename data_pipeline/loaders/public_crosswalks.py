"""Keep official crosswalk points separate from inferred OSM route topology."""

import json
from pathlib import Path

from loaders.postgis import database_connection


def load_public_crosswalks(path: Path) -> int:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM public_crosswalks WHERE source = %s", ("incheon-road-poi-2022",))
            for feature in features:
                p = feature["properties"]
                longitude, latitude = feature["geometry"]["coordinates"]
                cursor.execute(
                    """INSERT INTO public_crosswalks
                    (source, source_id, source_dataset, source_url, reference_date, geom)
                    VALUES (%s, %s, %s, %s, %s,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179))""",
                    ("incheon-road-poi-2022", p["source_id"], p["source_dataset"],
                     p["source_url"], p["reference_date"], longitude, latitude),
                )
    return len(features)
