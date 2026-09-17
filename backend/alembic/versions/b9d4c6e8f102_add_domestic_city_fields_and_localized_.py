"""Add domestic city fields and localized activity metadata

Revision ID: b9d4c6e8f102
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9d4c6e8f102"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cities", sa.Column("name_zh", sa.String(length=100), nullable=True))
    op.add_column("cities", sa.Column("country_zh", sa.String(length=100), nullable=True))
    op.add_column("cities", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("cities", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column(
        "cities",
        sa.Column("is_domestic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_cities_is_domestic"), "cities", ["is_domestic"], unique=False)

    op.add_column("activities", sa.Column("name_zh", sa.String(length=200), nullable=True))
    op.add_column("activities", sa.Column("description_zh", sa.Text(), nullable=True))

    op.execute("UPDATE cities SET name_zh = name WHERE name_zh IS NULL")
    op.execute("UPDATE cities SET country_zh = country WHERE country_zh IS NULL")
    op.execute("UPDATE activities SET name_zh = name WHERE name_zh IS NULL")
    op.execute("UPDATE activities SET description_zh = description WHERE description_zh IS NULL")

    op.alter_column("cities", "is_domestic", server_default=None)


def downgrade() -> None:
    op.drop_column("activities", "description_zh")
    op.drop_column("activities", "name_zh")

    op.drop_index(op.f("ix_cities_is_domestic"), table_name="cities")
    op.drop_column("cities", "is_domestic")
    op.drop_column("cities", "longitude")
    op.drop_column("cities", "latitude")
    op.drop_column("cities", "country_zh")
    op.drop_column("cities", "name_zh")
