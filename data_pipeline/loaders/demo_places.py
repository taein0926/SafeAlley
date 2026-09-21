"""Load address-level destinations for short walking-route demos."""

from loaders.postgis import database_connection


def load_demo_places() -> int:
    # 에이스오피스텔: https://jusoga.com/b/2817010500103750004000001/
    # 그린빌라트: https://jusoga.com/b/2817010500103950002214926/
    # These are address-level points, not verified pedestrian entrances.
    places = [
        (
            "demo-address",
            "seokbawi-30-ace-officetel",
            "에이스오피스텔",
            [],
            "residence",
            "인천광역시 미추홀구 석바위로 30 (도화동)",
            126.67632980629,
            37.460640860941,
        ),
        (
            "demo-address",
            "seokbawi-5-18-28-green-villat",
            "그린빌라트",
            [],
            "residence",
            "인천광역시 미추홀구 석바위로5번길 18-28 (도화동)",
            126.67443598537,
            37.461836939149,
        ),
    ]
    with database_connection() as connection:
        with connection.cursor() as cursor:
            for place in places:
                cursor.execute(
                    """
                    INSERT INTO places (
                        source, source_id, name, aliases, category, address, geom
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 5179)
                    )
                    ON CONFLICT (source, source_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        aliases = EXCLUDED.aliases,
                        category = EXCLUDED.category,
                        address = EXCLUDED.address,
                        geom = EXCLUDED.geom
                    """,
                    place,
                )
    return len(places)
