import os

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config.settings import DATABASE_URL, DB_NAME, DB_USER, DB_PASSWORD
from models.db_models import Base

# When running on Cloud Run, CLOUD_SQL_CONNECTION is set to
# "project:region:instance" and we connect via the Cloud SQL Python Connector
# (IAM auth, no IP whitelisting needed).
# Locally, we connect directly via DATABASE_URL (docker postgres or Cloud SQL public IP).
_CLOUD_SQL_CONNECTION = os.getenv("CLOUD_SQL_CONNECTION")

if _CLOUD_SQL_CONNECTION:
    from google.cloud.sql.connector import Connector
    _connector = Connector()

    def _get_conn():
        return _connector.connect(
            _CLOUD_SQL_CONNECTION,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )

    engine = create_engine(
        "postgresql+pg8000://",
        creator=_get_conn,
        pool_size=5,
        max_overflow=10,
    )
    logger.info(f"DB: Cloud SQL connector → {_CLOUD_SQL_CONNECTION}")
else:
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
    logger.info(f"DB: direct connection → {DATABASE_URL.split('@')[-1]}")

SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def upgrade_schema():
    """Apply idempotent ALTER TABLE statements for columns that create_all() cannot add."""
    stmts = [
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'linkedin'",
        "ALTER TABLE jobsql ALTER COLUMN description DROP NOT NULL",
        "ALTER TABLE jobsql ALTER COLUMN location DROP NOT NULL",
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS skills_extracted JSONB",
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS experience_years INTEGER",
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP",
        "CREATE EXTENSION IF NOT EXISTS vector",
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS embedding vector(768)",
        "CREATE INDEX IF NOT EXISTS idx_jobsql_embedding ON jobsql USING hnsw (embedding vector_cosine_ops)",
        "ALTER TABLE jobsql ADD COLUMN IF NOT EXISTS added_at INTEGER DEFAULT (EXTRACT(EPOCH FROM NOW()) / 3600)::INTEGER",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
                logger.debug(f"Schema upgrade applied: {stmt}")
            except Exception as e:
                logger.debug(f"Schema upgrade skipped ({stmt}): {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
