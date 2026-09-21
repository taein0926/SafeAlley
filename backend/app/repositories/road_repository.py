from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from app.db.connection import connect_database


@dataclass(frozen=True)
class BoundingBox:
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float


@dataclass(frozen=True)
class NearestRoadNode:
    node_id: int
    x: float
    y: float
    longitude: float
    latitude: float
    distance_m: float


@dataclass(frozen=True)
class RoutingRoadSegment:
    id: int
    source_id: str
    name: str | None
    source_node_id: int
    target_node_id: int
    forward_allowed: bool
    reverse_allowed: bool
    length_m: float
    streetlight_score: float
    cctv_score: float
    population_score: float
    safety_score: float
    streetlight_data_available: bool
    source_x: float
    source_y: float
    target_x: float
    target_y: float
    coordinates: tuple[tuple[float, float], ...]
    walkability_factor: float
    crossing_node_ids: tuple[int, ...]
    is_steps: bool
    sidewalk_confirmed: bool
    incline_percent: float | None
    walkability_class: str | None = None
    field_status: str = "unverified"


class RoadRepositoryError(RuntimeError):
    """Raised when road data cannot be read from PostGIS."""


def list_road_segments(
    bbox: BoundingBox | None = None,
    source: str | None = None,
) -> list[dict[str, object]]:
    condition_parts: list[str] = []
    parameters: list[object] = []

    if bbox is not None:
        condition_parts.append(
            """geom && ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326),
                5179
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
        condition_parts.append("source = %s")
        parameters.append(source)

    conditions = (
        f"WHERE {' AND '.join(condition_parts)}" if condition_parts else ""
    )

    query = f"""
        SELECT
            id,
            source,
            source_id,
            name,
            source_node_id,
            target_node_id,
            forward_allowed,
            reverse_allowed,
            ROUND(length_m::numeric, 2)::double precision AS length_m,
            streetlight_score::double precision AS streetlight_score,
            cctv_score::double precision AS cctv_score,
            population_score::double precision AS population_score,
            safety_score::double precision AS safety_score,
            ST_AsGeoJSON(ST_Transform(geom, 4326), 6)::json AS geometry
        FROM road_segments
        {conditions}
        ORDER BY id
    """

    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())
    except psycopg.Error as exc:
        raise RoadRepositoryError("Failed to query road segments") from exc


def find_nearest_road_node(
    longitude: float,
    latitude: float,
    source: str | None = None,
) -> NearestRoadNode | None:
    query = """
        WITH input_point AS (
            SELECT ST_Transform(
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                5179
            ) AS geom
        ),
        selected_roads AS (
            SELECT *
            FROM road_segments
            WHERE (%s::text IS NULL OR source = %s)
        ),
        node_candidates AS (
            SELECT source_node_id AS node_id, ST_StartPoint(geom) AS geom
            FROM selected_roads
            UNION ALL
            SELECT target_node_id AS node_id, ST_EndPoint(geom) AS geom
            FROM selected_roads
        ),
        graph_nodes AS (
            SELECT DISTINCT ON (node_id) node_id, geom
            FROM node_candidates
            ORDER BY node_id
        )
        SELECT
            node_id,
            ST_X(graph_nodes.geom) AS x,
            ST_Y(graph_nodes.geom) AS y,
            ST_X(ST_Transform(graph_nodes.geom, 4326)) AS longitude,
            ST_Y(ST_Transform(graph_nodes.geom, 4326)) AS latitude,
            ST_Distance(graph_nodes.geom, input_point.geom) AS distance_m
        FROM graph_nodes
        CROSS JOIN input_point
        ORDER BY distance_m
        LIMIT 1
    """

    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, (longitude, latitude, source, source))
                row = cursor.fetchone()
    except psycopg.Error as exc:
        raise RoadRepositoryError("Failed to find the nearest road node") from exc

    if row is None:
        return None

    return NearestRoadNode(
        node_id=row["node_id"],
        x=float(row["x"]),
        y=float(row["y"]),
        longitude=float(row["longitude"]),
        latitude=float(row["latitude"]),
        distance_m=float(row["distance_m"]),
    )


def list_routing_road_segments(
    source: str | None = None,
) -> list[RoutingRoadSegment]:
    query = """
        SELECT
            id,
            source_id,
            name,
            source_node_id,
            target_node_id,
            forward_allowed,
            reverse_allowed,
            length_m,
            streetlight_score,
            cctv_score,
            population_score,
            safety_score,
            COALESCE(properties->>'safety_data_status', '') LIKE 'streetlight-%%'
                AS streetlight_data_available,
            COALESCE((properties->>'walkability_factor')::double precision, 1.0)
                AS walkability_factor,
            COALESCE(properties->'crossing_node_ids', '[]'::jsonb)
                AS crossing_node_ids,
            COALESCE((properties->>'is_steps')::boolean, false) AS is_steps,
            COALESCE((properties->>'sidewalk_confirmed')::boolean, false)
                AS sidewalk_confirmed,
            properties->>'walkability_class' AS walkability_class,
            COALESCE(properties->>'field_status', 'unverified') AS field_status,
            COALESCE(
                (properties->>'dem_incline_percent')::double precision,
                (properties->>'incline_percent')::double precision
            ) AS incline_percent,
            ST_X(ST_StartPoint(geom)) AS source_x,
            ST_Y(ST_StartPoint(geom)) AS source_y,
            ST_X(ST_EndPoint(geom)) AS target_x,
            ST_Y(ST_EndPoint(geom)) AS target_y,
            ST_AsGeoJSON(ST_Transform(geom, 4326), 9)::json AS geometry
        FROM road_segments
        WHERE (%s::text IS NULL OR source = %s)
        ORDER BY id
    """

    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, (source, source))
                rows = cursor.fetchall()
    except psycopg.Error as exc:
        raise RoadRepositoryError("Failed to load the road graph") from exc

    return [
        RoutingRoadSegment(
            id=row["id"],
            source_id=row["source_id"],
            name=row["name"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            forward_allowed=row["forward_allowed"],
            reverse_allowed=row["reverse_allowed"],
            length_m=float(row["length_m"]),
            streetlight_score=float(row["streetlight_score"]),
            cctv_score=float(row["cctv_score"]),
            population_score=float(row["population_score"]),
            safety_score=float(row["safety_score"]),
            streetlight_data_available=bool(row["streetlight_data_available"]),
            walkability_factor=float(row["walkability_factor"]),
            crossing_node_ids=tuple(int(value) for value in row["crossing_node_ids"]),
            is_steps=bool(row["is_steps"]),
            sidewalk_confirmed=bool(row["sidewalk_confirmed"]),
            walkability_class=row["walkability_class"],
            field_status=row["field_status"],
            incline_percent=(
                float(row["incline_percent"])
                if row["incline_percent"] is not None
                else None
            ),
            source_x=float(row["source_x"]),
            source_y=float(row["source_y"]),
            target_x=float(row["target_x"]),
            target_y=float(row["target_y"]),
            coordinates=tuple(
                (float(coordinate[0]), float(coordinate[1]))
                for coordinate in row["geometry"]["coordinates"]
            ),
        )
        for row in rows
    ]
