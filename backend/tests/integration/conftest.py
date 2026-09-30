import pytest

from app.db.connection import connect_database


TEST_SOURCE = "test-fixture"
TEST_BUILDING_SOURCE = "test-building-fixture"
TEST_STREETLIGHT_SOURCE = "test-streetlight-fixture"
TEST_CCTV_SOURCE = "test-cctv-fixture"
TEST_HELP_POINT_SOURCE = "test-help-point-fixture"
TEST_USER_ID = "test-route-user"

TEST_ROADS = (
    ("test-road-001", "짧고 낮은 계단 1", 9001, 9002, 10, "LINESTRING(126.679 37.4608, 126.681 37.4608)", "steps", True),
    ("test-road-002", "짧고 낮은 계단 2", 9002, 9004, 10, "LINESTRING(126.681 37.4608, 126.683 37.4608)", "steps", True),
    ("test-road-003", "길고 안전한 길 1", 9001, 9003, 100, "LINESTRING(126.679 37.4608, 126.681 37.4623)", "footway", False),
    ("test-road-004", "길고 안전한 길 2", 9003, 9004, 100, "LINESTRING(126.681 37.4623, 126.683 37.4608)", "footway", False),
)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_road_graph():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM route_selection_events WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute(
                "DELETE FROM route_recommendations WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute(
                "DELETE FROM user_route_preferences WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute("DELETE FROM road_segments WHERE source = %s", (TEST_SOURCE,))
            cursor.execute(
                "DELETE FROM buildings WHERE source = %s",
                (TEST_BUILDING_SOURCE,),
            )
            cursor.execute(
                "DELETE FROM streetlights WHERE source = %s",
                (TEST_STREETLIGHT_SOURCE,),
            )
            cursor.execute("DELETE FROM cctvs WHERE source = %s", (TEST_CCTV_SOURCE,))
            cursor.execute(
                "DELETE FROM help_points WHERE source = %s",
                (TEST_HELP_POINT_SOURCE,),
            )
            for (
                source_id,
                name,
                source_node,
                target_node,
                score,
                wkt,
                highway,
                is_steps,
            ) in TEST_ROADS:
                cursor.execute(
                    """
                    WITH transformed AS (
                        SELECT ST_Transform(ST_GeomFromText(%s, 4326), 5179) AS geom
                    )
                    INSERT INTO road_segments (
                        source, source_id, name, source_node_id, target_node_id,
                        geom, length_m, streetlight_score, cctv_score,
                        population_score, safety_score, properties
                    )
                    SELECT
                        %s, %s, %s, %s, %s, geom, ST_Length(geom), %s, %s, %s, %s,
                        jsonb_build_object(
                            'highway', %s::text,
                            'is_steps', %s::boolean,
                            'incline', CASE WHEN %s::boolean THEN 'up' ELSE NULL END,
                            'safety_data_status', 'streetlight-test-v1',
                            'walkability_factor', 1.0,
                            'sidewalk_confirmed', TRUE,
                            'osm_pedestrian', jsonb_build_object('version', 'test-known-v1', 'allowed', true, 'sidewalk_confirmed', true),
                            'field_status', 'verified_walkable'
                        )
                    FROM transformed
                    """,
                    (
                        wkt,
                        TEST_SOURCE,
                        source_id,
                        name,
                        source_node,
                        target_node,
                        score,
                        score,
                        score,
                        score,
                        highway,
                        is_steps,
                        is_steps,
                    ),
                )
            cursor.execute(
                """
                INSERT INTO buildings (
                    source, building_id, building_name, address, main_use,
                    building_area, total_floor_area, height_m, floors, geom
                )
                VALUES
                (
                    %s, 'building-001', '테스트 건물', '인천광역시 미추홀구',
                    '교육시설', 120.5, 480.0, 12.0, 4,
                    ST_Multi(ST_Transform(ST_GeomFromText(
                        'POLYGON((126.6800 37.4610,126.6802 37.4610,126.6802 37.4612,126.6800 37.4612,126.6800 37.4610))',
                        4326
                    ), 5179))
                ),
                (
                    %s, 'building-002', '테스트 다중 건물', NULL,
                    NULL, NULL, NULL, NULL, NULL,
                    ST_Multi(ST_Transform(ST_GeomFromText(
                        'MULTIPOLYGON(((126.6820 37.4610,126.6822 37.4610,126.6822 37.4612,126.6820 37.4612,126.6820 37.4610)))',
                        4326
                    ), 5179))
                )
                """,
                (TEST_BUILDING_SOURCE, TEST_BUILDING_SOURCE),
            )
            cursor.execute(
                """
                INSERT INTO road_safety_segments (
                    road_id, segment_index, length_m, geom,
                    nearest_light_distance_m, nearby_light_count,
                    light_density, dark_gap_proxy_m, distance_score,
                    density_score, gap_score, streetlight_score,
                    nearest_cctv_distance_m, nearby_cctv_count, cctv_density,
                    cctv_gap_proxy_m, cctv_score,
                    nearest_help_point_distance_m,
                    nearest_help_point_category, help_point_score,
                    safety_score, analysis_version
                )
                SELECT
                    id, 0, length_m, geom, 4.5, 2, 1.25, 7.0,
                    80, 70, 75, 82.0,
                    12.0, 3, 2.5, 18.0, 68.0,
                    25.0, 'police', 74.0, 76.5, 'test-composite-v1'
                FROM road_segments
                WHERE source = %s
                """,
                (TEST_SOURCE,),
            )
            cursor.execute(
                """
                INSERT INTO streetlights (
                    source, source_id, pole_name, cabinet_name, label_no,
                    longitude, latitude, geom
                )
                VALUES (
                    %s, 'light-001', '테스트 가로등', 'A분전함', 'A-1',
                    126.6800, 37.4610,
                    ST_Transform(ST_SetSRID(ST_MakePoint(126.6800, 37.4610), 4326), 5179)
                )
                """,
                (TEST_STREETLIGHT_SOURCE,),
            )
            cursor.execute(
                """
                INSERT INTO cctvs (
                    source, source_id, management_agency, road_address,
                    purpose, camera_count, longitude, latitude, geom,
                    is_safety_cctv
                ) VALUES (
                    %s, 'cctv-001', '테스트 기관', '인천광역시 미추홀구',
                    '방범', 2, 126.6801, 37.4611,
                    ST_Transform(ST_SetSRID(ST_MakePoint(126.6801, 37.4611), 4326), 5179),
                    TRUE
                )
                """,
                (TEST_CCTV_SOURCE,),
            )
            cursor.execute(
                """
                INSERT INTO help_points (
                    source, external_id, name, category, address, geom
                ) VALUES (
                    %s, 'help-001', '테스트 경찰시설', 'police',
                    '인천광역시 미추홀구',
                    ST_Transform(ST_SetSRID(ST_MakePoint(126.6802, 37.4612), 4326), 5179)
                )
                """,
                (TEST_HELP_POINT_SOURCE,),
            )

    yield

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM route_selection_events WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute(
                "DELETE FROM route_recommendations WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute(
                "DELETE FROM user_route_preferences WHERE user_id = %s",
                (TEST_USER_ID,),
            )
            cursor.execute(
                "DELETE FROM streetlights WHERE source = %s",
                (TEST_STREETLIGHT_SOURCE,),
            )
            cursor.execute("DELETE FROM cctvs WHERE source = %s", (TEST_CCTV_SOURCE,))
            cursor.execute(
                "DELETE FROM help_points WHERE source = %s",
                (TEST_HELP_POINT_SOURCE,),
            )
            cursor.execute("DELETE FROM road_segments WHERE source = %s", (TEST_SOURCE,))
            cursor.execute(
                "DELETE FROM buildings WHERE source = %s",
                (TEST_BUILDING_SOURCE,),
            )
