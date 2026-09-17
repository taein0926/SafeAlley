from analysis.safety_components import run_safety_component_analysis
from loaders.postgis import database_connection


ROAD_SOURCE = "test-component-roads"
CCTV_SOURCE = "test-component-cctvs"
HELP_SOURCE = "test-component-help"


def _cleanup() -> None:
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM road_segments WHERE source = %s", (ROAD_SOURCE,))
            cursor.execute("DELETE FROM cctvs WHERE source = %s", (CCTV_SOURCE,))
            cursor.execute("DELETE FROM help_points WHERE source = %s", (HELP_SOURCE,))


def test_postgis_composite_analysis_keeps_components_and_metrics() -> None:
    _cleanup()
    try:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO road_segments (
                        source, source_id, source_node_id, target_node_id,
                        geom, length_m, streetlight_score, cctv_score,
                        population_score, safety_score
                    )
                    SELECT %s, values.source_id, values.source_node, values.target_node,
                           geom, ST_Length(geom), values.light_score, 0, 0,
                           values.light_score
                    FROM (
                        VALUES
                          ('road-a', 1::bigint, 2::bigint, 80::numeric,
                           ST_Transform(ST_GeomFromText(
                             'LINESTRING(126.6800 37.4600,126.6803 37.4600)', 4326
                           ), 5179)),
                          ('road-b', 2::bigint, 3::bigint, 40::numeric,
                           ST_Transform(ST_GeomFromText(
                             'LINESTRING(126.6820 37.4600,126.6823 37.4600)', 4326
                           ), 5179))
                    ) AS values(source_id, source_node, target_node, light_score, geom)
                    """,
                    (ROAD_SOURCE,),
                )
                cursor.execute(
                    """
                    INSERT INTO road_safety_segments (
                        road_id, segment_index, length_m, geom,
                        nearest_light_distance_m, nearby_light_count,
                        light_density, dark_gap_proxy_m, distance_score,
                        density_score, gap_score, streetlight_score,
                        safety_score, analysis_version
                    )
                    SELECT id, 0, length_m, geom, 10, 1, 1, 10,
                           50, 50, 50, streetlight_score,
                           streetlight_score, 'component-test'
                    FROM road_segments WHERE source = %s
                    """,
                    (ROAD_SOURCE,),
                )
                cursor.execute(
                    """
                    INSERT INTO cctvs (
                        source, source_id, purpose, longitude, latitude,
                        geom, is_safety_cctv
                    ) VALUES
                    (%s, 'near-a', '방범', 126.6801, 37.4600,
                     ST_Transform(ST_SetSRID(ST_MakePoint(126.6801,37.4600),4326),5179), TRUE),
                    (%s, 'near-b', '방범', 126.6830, 37.4600,
                     ST_Transform(ST_SetSRID(ST_MakePoint(126.6830,37.4600),4326),5179), TRUE)
                    """,
                    (CCTV_SOURCE, CCTV_SOURCE),
                )
                for category, longitude in (
                    ("police", 126.6801),
                    ("fire_station", 126.6810),
                    ("emergency_medical", 126.6830),
                ):
                    cursor.execute(
                        """
                        INSERT INTO help_points (
                            source, external_id, name, category, geom
                        ) VALUES (
                            %s, %s, %s, %s,
                            ST_Transform(ST_SetSRID(ST_MakePoint(%s,37.4600),4326),5179)
                        )
                        """,
                        (HELP_SOURCE, category, category, category, longitude),
                    )

        stats = run_safety_component_analysis(
            cctv_source=CCTV_SOURCE,
            help_point_source=HELP_SOURCE,
            road_source=ROAD_SOURCE,
        )
        assert stats["segment_count"] == 2
        assert stats["validation"] == {
            "null_score_count": 0,
            "non_finite_score_count": 0,
            "out_of_range_score_count": 0,
            "null_metric_count": 0,
        }
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM road_safety_segments analysis
                    JOIN road_segments road ON road.id = analysis.road_id
                    WHERE road.source = %s
                      AND analysis.streetlight_score BETWEEN 0 AND 100
                      AND analysis.cctv_score BETWEEN 0 AND 100
                      AND analysis.help_point_score BETWEEN 0 AND 100
                      AND analysis.safety_score BETWEEN 0 AND 100
                      AND analysis.nearest_cctv_distance_m IS NOT NULL
                      AND analysis.nearest_help_point_distance_m IS NOT NULL
                    """,
                    (ROAD_SOURCE,),
                )
                assert cursor.fetchone()[0] == 2
    finally:
        _cleanup()
