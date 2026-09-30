"""Allow custom route feedback while preserving historical route types."""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_route_selection_type", "route_selection_events", type_="check")
    op.create_check_constraint("ck_route_selection_type", "route_selection_events",
                               "selected_route_type IN ('shortest', 'balanced', 'safe', 'custom')")


def downgrade():
    # Never delete or relabel user feedback to satisfy an old constraint.
    op.execute("""DO $$ BEGIN IF EXISTS (
        SELECT 1 FROM route_selection_events WHERE selected_route_type='custom'
    ) THEN RAISE EXCEPTION 'Custom feedback exists; downgrade would lose compatibility'; END IF; END $$""")
    op.drop_constraint("ck_route_selection_type", "route_selection_events", type_="check")
    op.create_check_constraint("ck_route_selection_type", "route_selection_events",
                               "selected_route_type IN ('shortest', 'balanced', 'safe')")
