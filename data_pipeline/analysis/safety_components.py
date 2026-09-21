from typing import Any

from psycopg.rows import dict_row

from loaders.postgis import database_connection
from safety_component_config import SafetyComponentConfig


class SafetyComponentAnalysisError(RuntimeError):
    """Raised when CCTV/help-point composite analysis cannot be completed."""


def _distribution(cursor: Any, column: str, road_source: str) -> dict[str, float]:
    allowed = {
        "nearest_cctv_distance_m",
        "cctv_density",
        "cctv_gap_proxy_m",
        "streetlight_score",
        "cctv_score",
        "nearest_help_point_distance_m",
        "nearest_police_distance_m",
        "nearest_fire_station_distance_m",
        "nearest_emergency_medical_distance_m",
        "help_point_score",
        "safety_score",
    }
    if column not in allowed:
        raise ValueError(f"Unsupported distribution column: {column}")
    cursor.execute(
        f"""
        SELECT
            AVG(analysis.{column})::double precision AS average,
            MIN(analysis.{column})::double precision AS minimum,
            MAX(analysis.{column})::double precision AS maximum,
            percentile_cont(ARRAY[0.25, 0.5, 0.75, 0.9])
                WITHIN GROUP (ORDER BY analysis.{column}) AS percentiles
        FROM road_safety_segments analysis
        JOIN road_segments road ON road.id = analysis.road_id
        WHERE road.source = %s
          AND analysis.{column} IS NOT NULL
        """,
        (road_source,),
    )
    row = cursor.fetchone()
    if row["average"] is None:
        return {}
    percentiles = [float(value) for value in row["percentiles"]]
    return {
        "average": float(row["average"]),
        "minimum": float(row["minimum"]),
        "maximum": float(row["maximum"]),
        "p25": percentiles[0],
        "p50": percentiles[1],
        "p75": percentiles[2],
        "p90": percentiles[3],
    }


def run_safety_component_analysis(
    *,
    cctv_source: str = "michuhol-cctv-ai-ready",
    help_point_source: str = "ai-ready-help-points",
    road_source: str = "osm",
) -> dict[str, Any]:
    config = SafetyComponentConfig.from_environment()
    with database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT count(*) AS count
                FROM cctvs
                WHERE source = %s AND is_safety_cctv AND geom IS NOT NULL
                """,
                (cctv_source,),
            )
            safety_cctv_count = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT count(*) AS count FROM help_points WHERE source = %s",
                (help_point_source,),
            )
            help_point_count = int(cursor.fetchone()["count"])
            cursor.execute(
                """
                SELECT count(*) AS count
                FROM road_safety_segments analysis
                JOIN road_segments road ON road.id = analysis.road_id
                WHERE road.source = %s
                """,
                (road_source,),
            )
            segment_count = int(cursor.fetchone()["count"])
            if safety_cctv_count == 0:
                raise SafetyComponentAnalysisError(
                    "No valid safety CCTV rows are available; inspect purpose counts "
                    "and configure SAFETY_CCTV_PURPOSES with exact API values"
                )
            if help_point_count == 0:
                raise SafetyComponentAnalysisError(
                    "No valid AI-ready help points are available"
                )
            if segment_count == 0:
                raise SafetyComponentAnalysisError("No road safety segments are available")

            cursor.execute(
                """
                WITH nearest AS (
                    SELECT analysis.id, candidate.distance_m
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    CROSS JOIN LATERAL (
                        SELECT ST_Distance(analysis.geom, cctv.geom) AS distance_m
                        FROM cctvs cctv
                        WHERE cctv.source = %s
                          AND cctv.is_safety_cctv
                          AND cctv.geom IS NOT NULL
                        ORDER BY cctv.geom <-> analysis.geom
                        LIMIT 1
                    ) candidate
                    WHERE road.source = %s
                )
                UPDATE road_safety_segments analysis
                SET nearest_cctv_distance_m = nearest.distance_m
                FROM nearest
                WHERE analysis.id = nearest.id
                """,
                (cctv_source, road_source),
            )
            cursor.execute(
                """
                WITH counts AS (
                    SELECT analysis.id, count(cctv.id)::integer AS cctv_count
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    LEFT JOIN cctvs cctv
                      ON cctv.source = %s
                     AND cctv.is_safety_cctv
                     AND cctv.geom IS NOT NULL
                     AND ST_DWithin(analysis.geom, cctv.geom, %s)
                    WHERE road.source = %s
                    GROUP BY analysis.id
                )
                UPDATE road_safety_segments analysis
                SET nearby_cctv_count = counts.cctv_count,
                    cctv_density = counts.cctv_count * 100.0 / analysis.length_m
                FROM counts
                WHERE analysis.id = counts.id
                """,
                (cctv_source, config.cctv_search_radius_m, road_source),
            )
            cursor.execute(
                """
                WITH sample_points AS (
                    SELECT
                        analysis.id AS analysis_id,
                        sample.sample_index,
                        ST_LineInterpolatePoint(
                            analysis.geom,
                            LEAST(sample.sample_index * %s / analysis.length_m, 1.0)
                        ) AS geom
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    CROSS JOIN LATERAL generate_series(
                        0, CEIL(analysis.length_m / %s)::integer
                    ) AS sample(sample_index)
                    WHERE road.source = %s
                ),
                nearby AS (
                    SELECT
                        sample.analysis_id,
                        sample.sample_index,
                        sample.geom,
                        MIN(ST_Distance(sample.geom, cctv.geom)) AS distance_m
                    FROM sample_points sample
                    LEFT JOIN cctvs cctv
                      ON cctv.source = %s
                     AND cctv.is_safety_cctv
                     AND cctv.geom IS NOT NULL
                     AND ST_DWithin(sample.geom, cctv.geom, %s)
                    GROUP BY sample.analysis_id, sample.sample_index, sample.geom
                ),
                exact_distances AS (
                    SELECT
                        sample.analysis_id,
                        COALESCE(sample.distance_m, fallback.distance_m) AS distance_m
                    FROM nearby sample
                    LEFT JOIN LATERAL (
                        SELECT ST_Distance(sample.geom, cctv.geom) AS distance_m
                        FROM cctvs cctv
                        WHERE cctv.source = %s
                          AND cctv.is_safety_cctv
                          AND cctv.geom IS NOT NULL
                        ORDER BY cctv.geom <-> sample.geom
                        LIMIT 1
                    ) fallback ON sample.distance_m IS NULL
                ),
                gaps AS (
                    SELECT analysis_id, MAX(distance_m) AS distance_m
                    FROM exact_distances
                    GROUP BY analysis_id
                )
                UPDATE road_safety_segments analysis
                SET cctv_gap_proxy_m = gaps.distance_m
                FROM gaps
                WHERE analysis.id = gaps.analysis_id
                """,
                (
                    config.cctv_sample_interval_m,
                    config.cctv_sample_interval_m,
                    road_source,
                    cctv_source,
                    config.cctv_candidate_search_radius_m,
                    cctv_source,
                ),
            )
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT
                        analysis.id,
                        percent_rank() OVER (
                            ORDER BY analysis.nearest_cctv_distance_m
                        ) AS distance_rank,
                        percent_rank() OVER (
                            ORDER BY analysis.cctv_density
                        ) AS density_rank,
                        percent_rank() OVER (
                            ORDER BY analysis.cctv_gap_proxy_m
                        ) AS gap_rank
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                )
                UPDATE road_safety_segments analysis
                SET
                    cctv_distance_score = ROUND((100 * (1 - ranked.distance_rank))::numeric, 2),
                    cctv_density_score = ROUND((100 * ranked.density_rank)::numeric, 2),
                    cctv_gap_score = ROUND((100 * (1 - ranked.gap_rank))::numeric, 2),
                    cctv_score = ROUND(LEAST(100, GREATEST(0,
                        100 * (1 - ranked.distance_rank) * %s
                        + 100 * ranked.density_rank * %s
                        + 100 * (1 - ranked.gap_rank) * %s
                    ))::numeric, 2)
                FROM ranked
                WHERE analysis.id = ranked.id
                """,
                (
                    road_source,
                    config.cctv_distance_weight,
                    config.cctv_density_weight,
                    config.cctv_gap_weight,
                ),
            )

            cursor.execute(
                """
                WITH nearest AS (
                    SELECT
                        analysis.id,
                        candidate.help_point_id,
                        candidate.category,
                        candidate.distance_m
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    CROSS JOIN LATERAL (
                        SELECT
                            point.id AS help_point_id,
                            point.category,
                            ST_Distance(analysis.geom, point.geom) AS distance_m
                        FROM help_points point
                        WHERE point.source = %s
                        ORDER BY point.geom <-> analysis.geom
                        LIMIT 1
                    ) candidate
                    WHERE road.source = %s
                )
                UPDATE road_safety_segments analysis
                SET nearest_help_point_id = nearest.help_point_id,
                    nearest_help_point_category = nearest.category,
                    nearest_help_point_distance_m = nearest.distance_m
                FROM nearest
                WHERE analysis.id = nearest.id
                """,
                (help_point_source, road_source),
            )
            for category, column in (
                ("police", "nearest_police_distance_m"),
                ("fire_station", "nearest_fire_station_distance_m"),
                ("emergency_medical", "nearest_emergency_medical_distance_m"),
            ):
                cursor.execute(
                    f"""
                    WITH nearest AS (
                        SELECT analysis.id, candidate.distance_m
                        FROM road_safety_segments analysis
                        JOIN road_segments road ON road.id = analysis.road_id
                        LEFT JOIN LATERAL (
                            SELECT ST_Distance(analysis.geom, point.geom) AS distance_m
                            FROM help_points point
                            WHERE point.source = %s AND point.category = %s
                            ORDER BY point.geom <-> analysis.geom
                            LIMIT 1
                        ) candidate ON TRUE
                        WHERE road.source = %s
                    )
                    UPDATE road_safety_segments analysis
                    SET {column} = nearest.distance_m
                    FROM nearest
                    WHERE analysis.id = nearest.id
                    """,
                    (help_point_source, category, road_source),
                )
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT analysis.id,
                           percent_rank() OVER (
                               ORDER BY analysis.nearest_help_point_distance_m
                           ) AS distance_rank
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                )
                UPDATE road_safety_segments analysis
                SET help_point_score = ROUND(
                    LEAST(100, GREATEST(0, 100 * (1 - ranked.distance_rank)))::numeric,
                    2
                )
                FROM ranked
                WHERE analysis.id = ranked.id
                """,
                (road_source,),
            )
            cursor.execute(
                """
                UPDATE road_safety_segments analysis
                SET safety_score = ROUND(LEAST(100, GREATEST(0,
                        analysis.streetlight_score * %s
                        + analysis.cctv_score * %s
                        + analysis.help_point_score * %s
                    ))::numeric, 2),
                    analysis_version = 'composite-v1',
                    analyzed_at = NOW()
                FROM road_segments road
                WHERE road.id = analysis.road_id AND road.source = %s
                """,
                (
                    config.safety_streetlight_weight,
                    config.safety_cctv_weight,
                    config.safety_help_point_weight,
                    road_source,
                ),
            )
            cursor.execute(
                """
                WITH scores AS (
                    SELECT
                        analysis.road_id,
                        SUM(analysis.streetlight_score * analysis.length_m)
                            / SUM(analysis.length_m) AS streetlight_score,
                        SUM(analysis.cctv_score * analysis.length_m)
                            / SUM(analysis.length_m) AS cctv_score,
                        SUM(analysis.help_point_score * analysis.length_m)
                            / SUM(analysis.length_m) AS help_point_score,
                        SUM(analysis.safety_score * analysis.length_m)
                            / SUM(analysis.length_m) AS safety_score
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                    GROUP BY analysis.road_id
                )
                UPDATE road_segments road
                SET streetlight_score = ROUND(scores.streetlight_score::numeric, 2),
                    cctv_score = ROUND(scores.cctv_score::numeric, 2),
                    help_point_score = ROUND(scores.help_point_score::numeric, 2),
                    safety_score = ROUND(scores.safety_score::numeric, 2),
                    properties = jsonb_set(
                        properties, '{safety_data_status}',
                        '"streetlight-cctv-help-relative-v1"'::jsonb, true
                    ),
                    updated_at = NOW()
                FROM scores
                WHERE road.id = scores.road_id
                """,
                (road_source,),
            )

            cursor.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE analysis.streetlight_score IS NULL
                           OR analysis.cctv_score IS NULL
                           OR analysis.help_point_score IS NULL
                           OR analysis.safety_score IS NULL
                    ) AS null_score_count,
                    count(*) FILTER (
                        WHERE analysis.streetlight_score::text IN ('NaN','Infinity','-Infinity')
                           OR analysis.cctv_score::text IN ('NaN','Infinity','-Infinity')
                           OR analysis.help_point_score::text IN ('NaN','Infinity','-Infinity')
                           OR analysis.safety_score::text IN ('NaN','Infinity','-Infinity')
                    ) AS non_finite_score_count,
                    count(*) FILTER (
                        WHERE analysis.streetlight_score NOT BETWEEN 0 AND 100
                           OR analysis.cctv_score NOT BETWEEN 0 AND 100
                           OR analysis.help_point_score NOT BETWEEN 0 AND 100
                           OR analysis.safety_score NOT BETWEEN 0 AND 100
                    ) AS out_of_range_score_count,
                    count(*) FILTER (
                        WHERE analysis.nearest_cctv_distance_m IS NULL
                           OR analysis.nearby_cctv_count IS NULL
                           OR analysis.cctv_density IS NULL
                           OR analysis.cctv_gap_proxy_m IS NULL
                           OR analysis.nearest_help_point_distance_m IS NULL
                    ) AS null_metric_count
                FROM road_safety_segments analysis
                JOIN road_segments road ON road.id = analysis.road_id
                WHERE road.source = %s
                """,
                (road_source,),
            )
            validation = dict(cursor.fetchone())
            if any(int(value) for value in validation.values()):
                raise SafetyComponentAnalysisError(
                    f"Composite safety validation failed: {validation}"
                )

            distributions = {
                column: _distribution(cursor, column, road_source)
                for column in (
                    "nearest_cctv_distance_m",
                    "cctv_density",
                    "cctv_gap_proxy_m",
                    "cctv_score",
                    "nearest_help_point_distance_m",
                    "nearest_police_distance_m",
                    "nearest_fire_station_distance_m",
                    "nearest_emergency_medical_distance_m",
                    "streetlight_score",
                    "help_point_score",
                    "safety_score",
                )
            }

    return {
        "segment_count": segment_count,
        "safety_cctv_count": safety_cctv_count,
        "help_point_count": help_point_count,
        "validation": validation,
        "config": config.__dict__,
        "distributions": distributions,
    }
