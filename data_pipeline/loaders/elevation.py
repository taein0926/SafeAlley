"""Apply DEM grade estimates without replacing roads or their safety scores."""

import json
from pathlib import Path

from loaders.postgis import database_connection


def load_road_slopes(path: Path, *, road_source: str = "osm") -> int:
    document = json.loads(path.read_text(encoding="utf-8"))
    metadata = document["metadata"]
    estimates = document["estimates"]
    with database_connection() as connection:
        with connection.cursor() as cursor:
            # Invalidate older DEM values, but preserve explicit OSM inclines.
            cursor.execute(
                """UPDATE road_segments SET properties = properties
                    - 'dem_incline_percent' - 'dem_elevation_change_m'
                    - 'dem_source' - 'dem_cell_size_m'
                    WHERE source = %s""",
                (road_source,),
            )
            for estimate in estimates:
                cursor.execute(
                    """UPDATE road_segments SET properties = properties || %s::jsonb
                    WHERE source = %s AND source_id = %s""",
                    (
                        json.dumps(
                            {
                                "dem_incline_percent": estimate["incline_percent"],
                                "dem_elevation_change_m": estimate["elevation_change_m"],
                                "dem_source": metadata,
                                "dem_cell_size_m": metadata["cell_size_m"],
                            }
                        ),
                        road_source,
                        estimate["source_id"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"Road edge not found: {estimate['source_id']}")
    return len(estimates)
