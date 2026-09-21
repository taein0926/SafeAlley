"""Add route recommendation feedback and learned preferences.

Revision ID: 0007
Revises: 0006
"""

from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE route_recommendations (
            id UUID PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL,
            candidates JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX ix_route_recommendations_user_created
            ON route_recommendations (user_id, created_at DESC);

        CREATE TABLE route_selection_events (
            id BIGSERIAL PRIMARY KEY,
            recommendation_id UUID NOT NULL REFERENCES route_recommendations(id),
            user_id VARCHAR(128) NOT NULL,
            selected_route_type VARCHAR(32) NOT NULL,
            selected_metrics JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_route_selection_recommendation UNIQUE (recommendation_id),
            CONSTRAINT ck_route_selection_type CHECK (
                selected_route_type IN ('shortest', 'balanced', 'safe')
            )
        );

        CREATE INDEX ix_route_selection_events_user_created
            ON route_selection_events (user_id, created_at DESC);

        CREATE TABLE user_route_preferences (
            user_id VARCHAR(128) NOT NULL,
            factor VARCHAR(64) NOT NULL,
            weight DOUBLE PRECISION NOT NULL,
            observations INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, factor),
            CONSTRAINT ck_user_route_preference_weight CHECK (
                weight BETWEEN 0 AND 1
            ),
            CONSTRAINT ck_user_route_preference_observations CHECK (
                observations > 0
            )
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS user_route_preferences;
        DROP TABLE IF EXISTS route_selection_events;
        DROP TABLE IF EXISTS route_recommendations;
        """
    )
