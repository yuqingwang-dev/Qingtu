"""Add provider provenance and stable external POI identity."""
from alembic import op
import sqlalchemy as sa

revision = "c2e6f8a90123"
down_revision = "b9d4c6e8f102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activities", sa.Column("provider_name", sa.String(30), nullable=True))
    op.add_column("activities", sa.Column("provider_poi_id", sa.String(100), nullable=True))
    op.add_column("activities", sa.Column("provider_metadata", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_activity_provider_poi", "activities", ["city_id", "provider_name", "provider_poi_id"])


def downgrade():
    op.drop_constraint("uq_activity_provider_poi", "activities", type_="unique")
    op.drop_column("activities", "provider_metadata")
    op.drop_column("activities", "provider_poi_id")
    op.drop_column("activities", "provider_name")
