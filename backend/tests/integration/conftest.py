import pytest

from app.db.connection import connect_database


TEST_SOURCE = "test-fixture"
TEST_BUILDING_SOURCE = "test-building-fixture"
TEST_STREETLIGHT_SOURCE = "test-streetlight-fixture"

TEST_ROADS = (
    ("test-road-001", "짧고 낮은 길 1", 9001, 9002, 10, "LINESTRING(126.679 37.4608, 126.681 37.4608)"),
    ("test-road-002", "짧고 낮은 길 2", 9002, 9004, 10, "LINESTRING(126.681 37.4608, 126.683 37.4608)"),
    ("test-road-003", "길고 안전한 길 1", 9001, 9003, 100, "LINESTRING(126.679 37.4608, 126.681 37.4623)"),
    ("test-road-004", "길고 안전한 길 2", 9003, 9004, 100, "LINESTRING(126.681 37.4623, 126.683 37.4608)"),
)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_road_graph():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM road_segments WHERE source = %s", (TEST_SOURCE,))
            cursor.execute(
                "DELETE FROM buildings WHERE source = %s",
                (TEST_BUILDING_SOURCE,),
            )
            cursor.execute(
                "DELETE FROM streetlights WHERE source = %s",
                (TEST_STREETLIGHT_SOURCE,),
            )
            for source_id, name, source_node, target_node, score, wkt in TEST_ROADS:
                cursor.execute(
                    """
                    WITH transformed AS (
                        SELECT ST_Transform(ST_GeomFromText(%s, 4326), 5179) AS geom
                    )
                    INSERT INTO road_segments (
                        source, source_id, name, source_node_id, target_node_id,
                        geom, length_m, streetlight_score, cctv_score,
                        population_score, safety_score
                    )
                    SELECT
                        %s, %s, %s, %s, %s, geom, ST_Length(geom), %s, %s, %s, %s
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
                    density_score, gap_score, safety_score, analysis_version
                )
                SELECT
                    id, 0, length_m, geom, 4.5, 2, 1.25, 7.0,
                    80, 70, 75, 76.5, 'test-v1'
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

    yield

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM streetlights WHERE source = %s",
                (TEST_STREETLIGHT_SOURCE,),
            )
            cursor.execute("DELETE FROM road_segments WHERE source = %s", (TEST_SOURCE,))
            cursor.execute(
                "DELETE FROM buildings WHERE source = %s",
                (TEST_BUILDING_SOURCE,),
            )
