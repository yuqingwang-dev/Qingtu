"""Schema baseline tests.

Two complementary checks:

1. Static drift checks (always run, no DB required): verify every ORM table and
   column is created by some Alembic migration, so a fresh `alembic upgrade head`
   on Postgres reproduces the ORM schema. This catches the regression class
   "added an ORM model/column but forgot a migration". The known
   `activity_embeddings.embedding_vec` ORM-as-JSON / migration-as-vector(1536)
   workaround is explicitly excluded.

2. Real `alembic upgrade head` on Postgres+pgvector (skip-gated): reproduces the
   full schema against a real DB. Skipped unless `RUN_SCHEMA_BASELINE=1` and a
   reachable `DATABASE_URL`; intended to run in the docker/CI environment.

Note: migrations use Postgres-specific DDL (`server_default=sa.text('now()')`,
`CREATE EXTENSION vector`), so they cannot be run on sqlite — hence the static
approach for the always-on check.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import app.db.models  # noqa: F401  — register all models on Base.metadata
from app.db.session import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"

# Tables created via raw SQL (op.execute) rather than op.create_table.
RAW_SQL_TABLES = {"activity_embeddings"}
# ORM table whose `embedding_vec` column type deliberately differs from the
# migration (ORM=JSON so the ORM works without pgvector; migration=vector(1536)).
EMBEDDINGS_TABLE = "activity_embeddings"


def _migration_sources() -> list[tuple[str, str]]:
    """Return (revision_id, source_text) for every migration file."""
    sources: list[tuple[str, str]] = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        sources.append((path.name, path.read_text(encoding="utf-8")))
    return sources


def _extract_create_table_names(source: str) -> set[str]:
    """Find `op.create_table('name'` / `op.create_table(\"name\"` occurrences."""
    return set(re.findall(r"op\.create_table\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)", source))


def _extract_add_columns(source: str) -> dict[str, set[str]]:
    """Find `op.add_column('table', sa.Column('col'` occurrences -> {table: {cols}}."""
    out: dict[str, set[str]] = {}
    for table, col in re.findall(
        r"op\.add_column\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*,\s*sa\.Column\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)",
        source,
    ):
        out.setdefault(table, set()).add(col)
    return out


def _extract_create_table_columns(source: str) -> dict[str, set[str]]:
    """Best-effort extract columns declared inside `op.create_table('t', ... sa.Column('c' ...)`."""
    out: dict[str, set[str]] = {}
    # Match each create_table block by scanning columns until the matching close.
    for m in re.finditer(
        r"op\.create_table\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"](.*?)(?:\n\)\s*$|\n    op\.)",
        source, re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        cols = set(re.findall(r"sa\.Column\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)", body))
        out.setdefault(table, set()).update(cols)
    return out


def test_every_orm_table_is_created_by_a_migration():
    """A fresh `alembic upgrade head` must create every ORM table."""
    created: set[str] = set()
    raw_created: set[str] = set()
    for _, src in _migration_sources():
        created |= _extract_create_table_names(src)
        # raw SQL op.execute creating a table (e.g. activity_embeddings).
        for name in re.findall(r"CREATE\s+TABLE[^;]*?([A-Za-z_][A-Za-z0-9_]*)", src, re.IGNORECASE):
            raw_created.add(name)
    orm_tables = set(Base.metadata.tables.keys())
    # activity_embeddings is created via raw SQL in a1b2c3d4.
    missing = orm_tables - created - RAW_SQL_TABLES
    assert not missing, f"ORM tables with no create_table migration: {missing}"
    assert EMBEDDINGS_TABLE in orm_tables


def test_orm_columns_covered_by_migrations():
    """Every ORM column (except the embeddings workaround) must appear in a migration."""
    migration_columns: dict[str, set[str]] = {}
    for _, src in _migration_sources():
        for table, cols in _extract_create_table_columns(src).items():
            migration_columns.setdefault(table, set()).update(cols)
        for table, cols in _extract_add_columns(src).items():
            migration_columns.setdefault(table, set()).update(cols)

    for table_name, table_obj in Base.metadata.tables.items():
        if table_name == EMBEDDINGS_TABLE:
            # embedding_vec is vector(1536) via raw SQL; ORM declares JSON on purpose.
            continue
        orm_cols = {c.name for c in table_obj.columns}
        mig_cols = migration_columns.get(table_name, set())
        missing = orm_cols - mig_cols
        assert not missing, (
            f"Table '{table_name}': ORM columns missing from migrations: {missing}"
        )


@pytest.mark.skipif(
    os.getenv("RUN_SCHEMA_BASELINE") != "1",
    reason="Set RUN_SCHEMA_BASELINE=1 to run the Postgres+pgvector upgrade test.",
)
def test_alembic_upgrade_head_creates_all_tables():
    """Reproducibility: `alembic upgrade head` on Postgres creates all ORM tables."""
    from sqlalchemy import create_engine, inspect

    from alembic import command
    from alembic.config import Config
    from app.config import settings

    database_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    engine = create_engine(database_url)
    try:
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DATABASE_URL not reachable: {exc}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_DIR))
    command.upgrade(cfg, "head")

    tables = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables.keys()) | {"alembic_version"}
    assert expected.issubset(tables), f"Missing tables after upgrade: {expected - tables}"
    # activity_embeddings must exist (created by the pgvector migration).
    assert EMBEDDINGS_TABLE in tables
