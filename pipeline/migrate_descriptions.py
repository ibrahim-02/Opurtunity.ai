"""
Migrate job descriptions from PostgreSQL → GCS.

Usage (run from repo root: job_scrapper/):
    python -m pipeline.migrate_descriptions
    python -m pipeline.migrate_descriptions --batch 100
    python -m pipeline.migrate_descriptions --source greenhouse
"""
import argparse
import sys
import time

from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal
from storage.gcs_client import GCSClient

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)


def fetch_pending(session, batch: int, source: str | None) -> list:
    if source:
        q = text("""
            SELECT id, company_name, title, description
            FROM jobsql
            WHERE description IS NOT NULL
              AND description NOT LIKE 'gs://%'
              AND source = :source
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch, "source": source}).fetchall()
    else:
        q = text("""
            SELECT id, company_name, title, description
            FROM jobsql
            WHERE description IS NOT NULL
              AND description NOT LIKE 'gs://%'
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch}).fetchall()


def run(batch: int, source: str | None, delay: float):
    logger.info("Connecting to database...")
    session = SessionLocal()

    logger.info("Connecting to GCS...")
    gcs = GCSClient()
    if not gcs.is_available():
        logger.error("Cannot reach GCS bucket — check gcp-key.json and bucket name")
        session.close()
        return

    rows = fetch_pending(session, batch, source)
    if not rows:
        logger.info("No jobs pending migration — all descriptions already in GCS or NULL.")
        session.close()
        return

    logger.info(f"Migrating {len(rows)} descriptions to GCS (source={source or 'all'})")
    counts = {"ok": 0, "error": 0}

    for i, (job_id, company, title, description) in enumerate(rows, 1):
        try:
            company = company or "Unknown Company"
            title = title or "Unknown Title"
            uri = gcs.upload_description(company, title, job_id, description)
            session.execute(
                text("UPDATE jobsql SET description = :uri WHERE id = :id"),
                {"uri": uri, "id": job_id},
            )
            session.commit()
            counts["ok"] += 1
            logger.info(f"  [{i}/{len(rows)}] {title} @ {company} → {uri}")
        except Exception as e:
            session.rollback()
            counts["error"] += 1
            logger.error(f"  [{i}/{len(rows)}] id={job_id} failed: {e}")
        time.sleep(delay)

    session.close()
    logger.info("=" * 50)
    logger.info(f"  Migrated : {counts['ok']}")
    logger.info(f"  Errors   : {counts['error']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate descriptions from DB to GCS")
    parser.add_argument("--batch", type=int, default=50, help="Jobs per run (default: 50)")
    parser.add_argument("--source", type=str, default=None, help="Filter: linkedin | greenhouse")
    parser.add_argument("--delay", type=float, default=0.1, help="Seconds between uploads (default: 0.1)")
    args = parser.parse_args()
    run(batch=args.batch, source=args.source, delay=args.delay)
