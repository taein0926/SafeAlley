import json
import os
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from safety_config import SafetyScoreWeights


UPSERT_ROAD_SQL = """
    WITH transformed AS (
        SELECT ST_Transform(
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
            5179
        ) AS geom
    )
    INSERT INTO road_segments (
        source,
        source_id,
        name,
        source_node_id,
        target_node_id,
        forward_allowed,
        reverse_allowed,
        geom,
        length_m,
        streetlight_score,
        cctv_score,
        population_score,
        safety_score,
        properties
    )
    SELECT
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        transformed.geom,
        ST_Length(transformed.geom),
        %s,
        %s,
        %s,
        %s,
        %s
    FROM transformed
    ON CONFLICT (source, source_id) DO UPDATE SET
        name = EXCLUDED.name,
        source_node_id = EXCLUDED.source_node_id,
        target_node_id = EXCLUDED.target_node_id,
        forward_allowed = EXCLUDED.forward_allowed,
        reverse_allowed = EXCLUDED.reverse_allowed,
        geom = EXCLUDED.geom,
        length_m = EXCLUDED.length_m,
        streetlight_score = EXCLUDED.streetlight_score,
        cctv_score = EXCLUDED.cctv_score,
        population_score = EXCLUDED.population_score,
        safety_score = EXCLUDED.safety_score,
        properties = EXCLUDED.properties,
        updated_at = NOW()
"""


def database_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "database"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "safealley"),
        user=os.getenv("POSTGRES_USER", "safealley"),
        password=os.getenv("POSTGRES_PASSWORD", "safealley-local-only"),
        connect_timeout=5,
    )


def load_road_segments(
    features: list[dict[str, Any]],
    replace_source: str | None = None,
) -> int:
    weights = SafetyScoreWeights.from_environment()
    with database_connection() as connection:
        with connection.cursor() as cursor:
            if replace_source is not None:
                cursor.execute(
                    "DELETE FROM road_segments WHERE source = %s",
                    (replace_source,),
                )
            for feature in features:
                properties = feature["properties"]
                streetlight_score = float(properties["streetlight_score"])
                cctv_score = float(properties["cctv_score"])
                population_score = float(properties["population_score"])
                safety_score = weights.calculate(
                    streetlight_score,
                    cctv_score,
                    population_score,
                )
                cursor.execute(
                    UPSERT_ROAD_SQL,
                    (
                        json.dumps(feature["geometry"]),
                        properties["source"],
                        properties["source_id"],
                        properties.get("name"),
                        properties["source_node_id"],
                        properties["target_node_id"],
                        properties.get("forward_allowed", True),
                        properties.get("reverse_allowed", True),
                        streetlight_score,
                        cctv_score,
                        population_score,
                        safety_score,
                        Jsonb(properties),
                    ),
                )

    return len(features)
