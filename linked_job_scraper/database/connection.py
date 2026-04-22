from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from loguru import logger

from config.settings import DATABASE_URL
from models.db_models import Base

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def upgrade_schema():
    """Apply column-level changes that create_all() cannot handle.

    SQLAlchemy's create_all() only creates missing tables — it never alters
    existing columns.  This function runs idempotent ALTER TABLE statements to
    bring an already-created table in line with the current model definition.
    Safe to call on every startup.
    """
    stmts = [
        # Allow NULL in columns that were previously NOT NULL
        "ALTER TABLE jobsql ALTER COLUMN description DROP NOT NULL",
        "ALTER TABLE jobsql ALTER COLUMN location DROP NOT NULL",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
                logger.debug(f"Schema upgrade applied: {stmt}")
            except Exception as e:
                # Ignore "column does not exist" or "already nullable" errors
                logger.debug(f"Schema upgrade skipped ({stmt}): {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
