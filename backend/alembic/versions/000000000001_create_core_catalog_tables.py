"""Create core city and activity catalog tables

Revision ID: 000000000001
Revises:
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "000000000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("time_zone", sa.String(length=50), nullable=True),
        sa.Column("default_currency", sa.String(length=10), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cities_id"), "cities", ["id"], unique=False)
    op.create_index(op.f("ix_cities_name"), "cities", ["name"], unique=True)

    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("base_cost", sa.Float(), nullable=True),
        sa.Column("avg_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activities_category"), "activities", ["category"], unique=False)
    op.create_index(op.f("ix_activities_city_id"), "activities", ["city_id"], unique=False)
    op.create_index(op.f("ix_activities_id"), "activities", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_activities_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_city_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_category"), table_name="activities")
    op.drop_table("activities")
    op.drop_index(op.f("ix_cities_name"), table_name="cities")
    op.drop_index(op.f("ix_cities_id"), table_name="cities")
    op.drop_table("cities")
