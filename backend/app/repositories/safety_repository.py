import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database
from app.repositories.road_repository import BoundingBox


class SafetyRepositoryError(RuntimeError):
    """Raised when streetlight safety data cannot be read from PostGIS."""


def _filters(
    *,
    bbox: BoundingBox | None,
    source: str | None,
    source_column: str,
    geometry_column: str,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    parameters: list[object] = []
    if bbox is not None:
        conditions.append(
            f"""{geometry_column} && ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326), 5179
            )"""
        )
        parameters.extend(
            [
                bbox.min_longitude,
                bbox.min_latitude,
                bbox.max_longitude,
                bbox.max_latitude,
            ]
        )
    if source is not None:
        conditions.append(f"{source_column} = %s")
        parameters.append(source)
    return (
        f"WHERE {' AND '.join(conditions)}" if conditions else "",
        parameters,
    )


def list_safety_segments(
    bbox: BoundingBox | None = None,
    source: str | None = None,
) -> list[dict[str, object]]:
    conditions, parameters = _filters(
        bbox=bbox,
        source=source,
        source_column="road.source",
        geometry_column="analysis.geom",
    )
    query = f"""
        SELECT
            analysis.id,
            analysis.id AS segment_id,
            analysis.road_id,
            road.source,
            road.source_id AS road_source_id,
            road.name,
            analysis.segment_index,
            ROUND(analysis.length_m::numeric, 2)::double precision AS length_m,
            ROUND(analysis.nearest_light_distance_m::numeric, 2)::double precision
                AS nearest_light_distance_m,
            analysis.nearby_light_count,
            ROUND(analysis.light_density::numeric, 3)::double precision AS light_density,
            ROUND(analysis.dark_gap_proxy_m::numeric, 2)::double precision AS dark_gap_proxy_m,
            analysis.distance_score::double precision AS distance_score,
            analysis.density_score::double precision AS density_score,
            analysis.gap_score::double precision AS gap_score,
            analysis.streetlight_score::double precision AS streetlight_score,
            ROUND(analysis.nearest_cctv_distance_m::numeric, 2)::double precision
                AS nearest_cctv_distance_m,
            analysis.nearby_cctv_count,
            ROUND(analysis.cctv_density::numeric, 3)::double precision AS cctv_density,
            ROUND(analysis.cctv_gap_proxy_m::numeric, 2)::double precision
                AS cctv_gap_proxy_m,
            analysis.cctv_score::double precision AS cctv_score,
            ROUND(analysis.nearest_help_point_distance_m::numeric, 2)::double precision
                AS nearest_help_point_distance_m,
            analysis.nearest_help_point_id,
            analysis.nearest_help_point_category,
            ROUND(analysis.nearest_police_distance_m::numeric, 2)::double precision
                AS nearest_police_distance_m,
            ROUND(analysis.nearest_fire_station_distance_m::numeric, 2)::double precision
                AS nearest_fire_station_distance_m,
            ROUND(analysis.nearest_emergency_medical_distance_m::numeric, 2)::double precision
                AS nearest_emergency_medical_distance_m,
            analysis.help_point_score::double precision AS help_point_score,
            analysis.safety_score::double precision AS safety_score,
            analysis.analysis_version,
            ST_AsGeoJSON(ST_Transform(analysis.geom, 4326), 7)::json AS geometry
        FROM road_safety_segments analysis
        JOIN road_segments road ON road.id = analysis.road_id
        {conditions}
        ORDER BY analysis.id
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise SafetyRepositoryError("Failed to query road safety segments") from exc


def list_streetlights(
    bbox: BoundingBox | None = None,
    source: str | None = None,
) -> list[dict[str, object]]:
    conditions, parameters = _filters(
        bbox=bbox,
        source=source,
        source_column="source",
        geometry_column="geom",
    )
    query = f"""
        SELECT
            id,
            source,
            source_id,
            pole_name,
            cabinet_name,
            label_no,
            matched_road_id,
            ROUND(matched_road_distance_m::numeric, 2)::double precision
                AS matched_road_distance_m,
            ST_AsGeoJSON(ST_Transform(geom, 4326), 7)::json AS geometry
        FROM streetlights
        {conditions}
        ORDER BY id
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise SafetyRepositoryError("Failed to query streetlights") from exc


def list_cctvs(
    bbox: BoundingBox | None = None,
    source: str | None = None,
    *,
    safety_only: bool = True,
) -> list[dict[str, object]]:
    conditions, parameters = _filters(
        bbox=bbox,
        source=source,
        source_column="source",
        geometry_column="geom",
    )
    extra_conditions = ["geom IS NOT NULL"]
    if safety_only:
        extra_conditions.append("is_safety_cctv")
    if conditions:
        conditions += " AND " + " AND ".join(extra_conditions)
    else:
        conditions = "WHERE " + " AND ".join(extra_conditions)
    query = f"""
        WITH selected AS (
            SELECT *
            FROM cctvs
            {conditions}
        )
        SELECT
            MIN(id) AS id,
            source,
            MIN(source_id) AS source_id,
            MIN(management_agency) AS management_agency,
            MIN(road_address) AS road_address,
            MIN(parcel_address) AS parcel_address,
            CASE WHEN COUNT(DISTINCT purpose) = 1 THEN MIN(purpose)
                 ELSE '복합 목적' END AS purpose,
            SUM(COALESCE(camera_count, 1))::integer AS camera_count,
            MAX(camera_pixels) AS camera_pixels,
            MIN(direction_info) AS direction_info,
            MAX(retention_days) AS retention_days,
            MIN(installed_at) AS installed_at,
            MIN(agency_phone) AS agency_phone,
            MAX(data_reference_date) AS data_reference_date,
            BOOL_OR(is_safety_cctv) AS is_safety_cctv,
            coordinate_quality,
            coordinate_source,
            MIN(longitude_precision_digits) AS longitude_precision_digits,
            MIN(latitude_precision_digits) AS latitude_precision_digits,
            COUNT(*)::integer AS location_record_count,
            ST_AsGeoJSON(ST_Transform(geom, 4326), 7)::json AS geometry
        FROM selected
        GROUP BY source, coordinate_quality, coordinate_source, geom
        ORDER BY MIN(id)
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise SafetyRepositoryError("Failed to query CCTV data") from exc


def list_help_points(
    bbox: BoundingBox | None = None,
    source: str | None = None,
    category: str | None = None,
) -> list[dict[str, object]]:
    conditions, parameters = _filters(
        bbox=bbox,
        source=source,
        source_column="source",
        geometry_column="geom",
    )
    if category is not None:
        conditions += (" AND " if conditions else "WHERE ") + "category = %s"
        parameters.append(category)
    query = f"""
        SELECT
            id, source, external_id, name, category, subtype, address,
            phone, emergency_phone, coordinate_quality, coordinate_status,
            coordinate_source, source_org, source_dataset, reference_date,
            ST_AsGeoJSON(ST_Transform(geom, 4326), 7)::json AS geometry
        FROM help_points
        {conditions}
        ORDER BY id
    """
    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise SafetyRepositoryError("Failed to query help points") from exc
