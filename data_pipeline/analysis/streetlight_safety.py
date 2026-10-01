from typing import Any
from contextlib import nullcontext

from psycopg.rows import dict_row

from loaders.postgis import database_connection
from streetlight_config import StreetlightAnalysisConfig


class StreetlightAnalysisError(RuntimeError):
    """Raised when PostGIS cannot produce a complete streetlight analysis."""


def _distribution(cursor: Any, column: str, road_source: str) -> dict[str, Any]:
    allowed_columns = {
        "nearest_light_distance_m",
        "light_density",
        "dark_gap_proxy_m",
        "safety_score",
    }
    if column not in allowed_columns:
        raise ValueError(f"Unsupported distribution column: {column}")
    cursor.execute(
        f"""
        SELECT
            AVG(rss.{column})::double precision AS average,
            percentile_cont(ARRAY[0.25, 0.5, 0.75, 0.9])
                WITHIN GROUP (ORDER BY rss.{column}) AS percentiles
        FROM road_safety_segments rss
        JOIN road_segments road ON road.id = rss.road_id
        WHERE road.source = %s
        """,
        (road_source,),
    )
    row = cursor.fetchone()
    percentiles = [float(value) for value in row["percentiles"]]
    return {
        "average": float(row["average"]),
        "p25": percentiles[0],
        "p50": percentiles[1],
        "p75": percentiles[2],
        "p90": percentiles[3],
    }


def run_streetlight_safety_analysis(
    *,
    streetlight_source: str,
    road_source: str = "osm",
    connection=None,
) -> dict[str, Any]:
    config = StreetlightAnalysisConfig.from_environment()

    with (nullcontext(connection) if connection is not None else database_connection()) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT count(*) AS count FROM streetlights WHERE source = %s",
                (streetlight_source,),
            )
            streetlight_count = int(cursor.fetchone()["count"])
            cursor.execute(
                """
                SELECT
                    count(*) AS road_count,
                    count(DISTINCT source_node_id) AS source_node_count,
                    count(DISTINCT target_node_id) AS target_node_count
                FROM road_segments
                WHERE source = %s
                """,
                (road_source,),
            )
            topology_before = dict(cursor.fetchone())
            if streetlight_count == 0:
                raise StreetlightAnalysisError(
                    f"No streetlights found for source={streetlight_source}"
                )
            if int(topology_before["road_count"]) == 0:
                raise StreetlightAnalysisError(
                    f"No roads found for source={road_source}"
                )

            cursor.execute(
                """
                WITH matches AS (
                    SELECT
                        light.id AS light_id,
                        nearest.id AS road_id,
                        ST_Distance(light.geom, nearest.geom) AS distance_m
                    FROM streetlights light
                    CROSS JOIN LATERAL (
                        SELECT road.id, road.geom
                        FROM road_segments road
                        WHERE road.source = %s
                        ORDER BY road.geom <-> light.geom
                        LIMIT 1
                    ) nearest
                    WHERE light.source = %s
                )
                UPDATE streetlights light
                SET
                    matched_road_id = matches.road_id,
                    matched_road_distance_m = matches.distance_m,
                    updated_at = NOW()
                FROM matches
                WHERE light.id = matches.light_id
                """,
                (road_source, streetlight_source),
            )

            cursor.execute(
                """
                DELETE FROM road_safety_segments analysis
                USING road_segments road
                WHERE analysis.road_id = road.id
                  AND road.source = %s
                """,
                (road_source,),
            )
            cursor.execute(
                """
                WITH selected_roads AS (
                    SELECT
                        id,
                        geom,
                        GREATEST(
                            1,
                            CEIL(ST_Length(geom) / %s)::integer
                        ) AS part_count
                    FROM road_segments
                    WHERE source = %s
                ),
                split_segments AS (
                    SELECT
                        road.id AS road_id,
                        part.segment_index,
                        ST_LineSubstring(
                            road.geom,
                            part.segment_index::double precision / road.part_count,
                            (part.segment_index + 1)::double precision
                                / road.part_count
                        ) AS geom
                    FROM selected_roads road
                    CROSS JOIN LATERAL generate_series(
                        0,
                        road.part_count - 1
                    ) AS part(segment_index)
                )
                INSERT INTO road_safety_segments (
                    road_id,
                    segment_index,
                    length_m,
                    geom,
                    nearest_light_distance_m,
                    nearby_light_count,
                    light_density,
                    dark_gap_proxy_m,
                    distance_score,
                    density_score,
                    gap_score,
                    streetlight_score,
                    safety_score,
                    analysis_version
                )
                SELECT
                    road_id,
                    segment_index,
                    ST_Length(geom),
                    geom,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    %s
                FROM split_segments
                WHERE NOT ST_IsEmpty(geom) AND ST_Length(geom) > 0
                """,
                (
                    config.segment_length_m,
                    road_source,
                    config.analysis_version,
                ),
            )

            cursor.execute(
                """
                WITH nearest_distances AS (
                    SELECT
                        analysis.id,
                        nearest.distance_m
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    CROSS JOIN LATERAL (
                        SELECT ST_Distance(analysis.geom, light.geom) AS distance_m
                        FROM streetlights light
                        WHERE light.source = %s
                        ORDER BY light.geom <-> analysis.geom
                        LIMIT 1
                    ) nearest
                    WHERE road.source = %s
                )
                UPDATE road_safety_segments analysis
                SET nearest_light_distance_m = nearest.distance_m
                FROM nearest_distances nearest
                WHERE analysis.id = nearest.id
                """,
                (streetlight_source, road_source),
            )

            cursor.execute(
                """
                WITH nearby_counts AS (
                    SELECT
                        analysis.id,
                        count(light.id)::integer AS light_count
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    LEFT JOIN streetlights light
                        ON light.source = %s
                       AND light.matched_road_id = analysis.road_id
                       AND ST_DWithin(
                            analysis.geom,
                            light.geom,
                            %s
                       )
                    WHERE road.source = %s
                    GROUP BY analysis.id
                )
                UPDATE road_safety_segments analysis
                SET
                    nearby_light_count = counts.light_count,
                    light_density = counts.light_count * 100.0 / analysis.length_m
                FROM nearby_counts counts
                WHERE analysis.id = counts.id
                """,
                (
                    streetlight_source,
                    config.search_radius_m,
                    road_source,
                ),
            )

            cursor.execute(
                """
                WITH sample_points AS (
                    SELECT
                        analysis.id AS analysis_id,
                        sample.sample_index,
                        ST_LineInterpolatePoint(
                            analysis.geom,
                            LEAST(
                                sample.sample_index * %s / analysis.length_m,
                                1.0
                            )
                        ) AS geom
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    CROSS JOIN LATERAL generate_series(
                        0,
                        CEIL(analysis.length_m / %s)::integer
                    ) AS sample(sample_index)
                    WHERE road.source = %s
                ),
                nearby_sample_distances AS (
                    SELECT
                        sample.analysis_id,
                        sample.sample_index,
                        sample.geom,
                        MIN(ST_Distance(sample.geom, light.geom)) AS distance_m
                    FROM sample_points sample
                    LEFT JOIN streetlights light
                        ON light.source = %s
                       AND ST_DWithin(sample.geom, light.geom, %s)
                    GROUP BY sample.analysis_id, sample.sample_index, sample.geom
                ),
                sample_distances AS (
                    SELECT
                        sample.analysis_id,
                        COALESCE(sample.distance_m, fallback.distance_m) AS distance_m
                    FROM nearby_sample_distances sample
                    LEFT JOIN LATERAL (
                        SELECT ST_Distance(sample.geom, light.geom) AS distance_m
                        FROM streetlights light
                        WHERE light.source = %s
                        ORDER BY light.geom <-> sample.geom
                        LIMIT 1
                    ) fallback ON sample.distance_m IS NULL
                ),
                maximum_distances AS (
                    SELECT analysis_id, MAX(distance_m) AS distance_m
                    FROM sample_distances
                    GROUP BY analysis_id
                )
                UPDATE road_safety_segments analysis
                SET dark_gap_proxy_m = gaps.distance_m
                FROM maximum_distances gaps
                WHERE analysis.id = gaps.analysis_id
                """,
                (
                    config.sample_interval_m,
                    config.sample_interval_m,
                    road_source,
                    streetlight_source,
                    config.candidate_search_radius_m,
                    streetlight_source,
                ),
            )

            cursor.execute(
                """
                WITH ranked AS (
                    SELECT
                        analysis.id,
                        percent_rank() OVER (
                            ORDER BY analysis.nearest_light_distance_m
                        ) AS distance_rank,
                        percent_rank() OVER (
                            ORDER BY analysis.light_density
                        ) AS density_rank,
                        percent_rank() OVER (
                            ORDER BY analysis.dark_gap_proxy_m
                        ) AS gap_rank
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                ),
                component_scores AS (
                    SELECT
                        id,
                        LEAST(100, GREATEST(0, 100 * (1 - distance_rank)))
                            AS distance_score,
                        LEAST(100, GREATEST(0, 100 * density_rank))
                            AS density_score,
                        LEAST(100, GREATEST(0, 100 * (1 - gap_rank)))
                            AS gap_score
                    FROM ranked
                )
                UPDATE road_safety_segments analysis
                SET
                    distance_score = ROUND(scores.distance_score::numeric, 2),
                    density_score = ROUND(scores.density_score::numeric, 2),
                    gap_score = ROUND(scores.gap_score::numeric, 2),
                    streetlight_score = ROUND(LEAST(100, GREATEST(0,
                        scores.distance_score * %s
                        + scores.density_score * %s
                        + scores.gap_score * %s
                    ))::numeric, 2),
                    safety_score = ROUND(LEAST(100, GREATEST(0,
                        scores.distance_score * %s
                        + scores.density_score * %s
                        + scores.gap_score * %s
                    ))::numeric, 2),
                    analyzed_at = NOW()
                FROM component_scores scores
                WHERE analysis.id = scores.id
                """,
                (
                    road_source,
                    config.distance_weight,
                    config.density_weight,
                    config.gap_weight,
                    config.distance_weight,
                    config.density_weight,
                    config.gap_weight,
                ),
            )

            cursor.execute(
                """
                WITH road_scores AS (
                    SELECT
                        analysis.road_id,
                        SUM(analysis.safety_score * analysis.length_m)
                            / SUM(analysis.length_m) AS safety_score
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                    GROUP BY analysis.road_id
                )
                UPDATE road_segments road
                SET
                    streetlight_score = ROUND(scores.safety_score::numeric, 2),
                    safety_score = ROUND(scores.safety_score::numeric, 2),
                    properties = jsonb_set(
                        properties,
                        '{safety_data_status}',
                        '"streetlight-relative-v1"'::jsonb,
                        true
                    ),
                    updated_at = NOW()
                FROM road_scores scores
                WHERE road.id = scores.road_id
                """,
                (road_source,),
            )

            cursor.execute(
                """
                SELECT
                    count(*) AS segment_count,
                    count(*) FILTER (
                        WHERE analysis.nearest_light_distance_m::text IN
                            ('NaN', 'Infinity', '-Infinity')
                           OR analysis.light_density::text IN
                            ('NaN', 'Infinity', '-Infinity')
                           OR analysis.dark_gap_proxy_m::text IN
                            ('NaN', 'Infinity', '-Infinity')
                           OR analysis.safety_score::text IN
                            ('NaN', 'Infinity', '-Infinity')
                    ) AS non_finite_count,
                    count(*) FILTER (
                        WHERE analysis.safety_score < 0
                           OR analysis.safety_score > 100
                    ) AS out_of_range_count,
                    count(*) FILTER (
                        WHERE ST_Length(analysis.geom) > %s + 0.001
                    ) AS oversized_segment_count,
                    count(*) FILTER (WHERE NOT ST_IsValid(analysis.geom))
                        AS invalid_geometry_count
                FROM road_safety_segments analysis
                JOIN road_segments road ON road.id = analysis.road_id
                WHERE road.source = %s
                """,
                (config.segment_length_m, road_source),
            )
            validation = dict(cursor.fetchone())

            cursor.execute(
                """
                SELECT
                    count(*) AS road_count,
                    count(DISTINCT source_node_id) AS source_node_count,
                    count(DISTINCT target_node_id) AS target_node_count
                FROM road_segments
                WHERE source = %s
                """,
                (road_source,),
            )
            topology_after = dict(cursor.fetchone())
            if topology_before != topology_after:
                raise StreetlightAnalysisError(
                    "Road graph topology changed during derived safety analysis"
                )
            if any(
                int(validation[key]) != 0
                for key in (
                    "non_finite_count",
                    "out_of_range_count",
                    "oversized_segment_count",
                    "invalid_geometry_count",
                )
            ):
                raise StreetlightAnalysisError(
                    f"Streetlight safety validation failed: {validation}"
                )

            distributions = {
                column: _distribution(cursor, column, road_source)
                for column in (
                    "nearest_light_distance_m",
                    "light_density",
                    "dark_gap_proxy_m",
                    "safety_score",
                )
            }

    return {
        "streetlight_count": streetlight_count,
        "road_count": int(topology_after["road_count"]),
        "segment_count": int(validation["segment_count"]),
        "topology_before": topology_before,
        "topology_after": topology_after,
        "validation": validation,
        "config": {
            "segment_length_m": config.segment_length_m,
            "search_radius_m": config.search_radius_m,
            "sample_interval_m": config.sample_interval_m,
            "candidate_search_radius_m": config.candidate_search_radius_m,
            "distance_weight": config.distance_weight,
            "density_weight": config.density_weight,
            "gap_weight": config.gap_weight,
        },
        "distributions": distributions,
    }
