import json
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from app.db.connection import connect_database


class PersonalizationRepositoryError(RuntimeError):
    """Raised when recommendation feedback cannot be stored or read."""


def save_recommendation(
    user_id: str,
    candidates: list[dict[str, object]],
) -> str:
    recommendation_id = str(uuid4())
    summaries = [
        {
            "route_type": candidate["route_type"],
            "metrics": candidate["metrics"],
        }
        for candidate in candidates
    ]
    try:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO route_recommendations (id, user_id, candidates)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (recommendation_id, user_id, json.dumps(summaries)),
                )
    except Exception as exc:
        raise PersonalizationRepositoryError(
            "Failed to save route recommendation"
        ) from exc
    return recommendation_id


def get_learned_preferences(user_id: str) -> dict[str, tuple[float, int]]:
    try:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT factor, weight, observations
                    FROM user_route_preferences
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                return {
                    str(factor): (float(weight), int(observations))
                    for factor, weight, observations in cursor.fetchall()
                }
    except Exception as exc:
        raise PersonalizationRepositoryError(
            "Failed to read learned route preferences"
        ) from exc


def record_selection(
    recommendation_id: str,
    user_id: str,
    selected_route_type: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    try:
        UUID(recommendation_id)
    except ValueError as exc:
        raise PersonalizationRepositoryError("Invalid recommendation id") from exc

    try:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT user_id, candidates
                    FROM route_recommendations
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (recommendation_id,),
                )
                recommendation = cursor.fetchone()
                if recommendation is None:
                    raise PersonalizationRepositoryError("Recommendation not found")
                if recommendation["user_id"] != user_id:
                    raise PersonalizationRepositoryError(
                        "Recommendation does not belong to this user"
                    )

                candidates = recommendation["candidates"]
                selected = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate["route_type"] == selected_route_type
                    ),
                    None,
                )
                if selected is None:
                    raise PersonalizationRepositoryError(
                        "Selected route is not part of this recommendation"
                    )

                cursor.execute(
                    """
                    INSERT INTO route_selection_events (
                        recommendation_id, user_id, selected_route_type,
                        selected_metrics
                    ) VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (recommendation_id) DO UPDATE SET
                        selected_route_type = EXCLUDED.selected_route_type,
                        selected_metrics = EXCLUDED.selected_metrics
                    """,
                    (
                        recommendation_id,
                        user_id,
                        selected_route_type,
                        json.dumps(selected["metrics"]),
                    ),
                )
                return candidates, selected
    except PersonalizationRepositoryError:
        raise
    except Exception as exc:
        raise PersonalizationRepositoryError("Failed to record route selection") from exc


def upsert_learned_preferences(
    user_id: str,
    learned_weights: dict[str, float],
) -> None:
    try:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                for factor, weight in learned_weights.items():
                    cursor.execute(
                        """
                        INSERT INTO user_route_preferences (
                            user_id, factor, weight, observations
                        ) VALUES (%s, %s, %s, 1)
                        ON CONFLICT (user_id, factor) DO UPDATE SET
                            weight = EXCLUDED.weight,
                            observations = user_route_preferences.observations + 1,
                            updated_at = NOW()
                        """,
                        (user_id, factor, weight),
                    )
    except Exception as exc:
        raise PersonalizationRepositoryError(
            "Failed to update learned route preferences"
        ) from exc
