"""
One-time migration: upload inline descriptions from Postgres to GCS.

Finds all jobs where description is plain text (not a gs:// URI),
uploads to GCS, and replaces the DB value with the gs:// URI.

Usage (from repo root):
    python -m pipeline.migrate_descriptions_to_gcs
    python -m pipeline.migrate_descriptions_to_gcs --batch 500 --dry-run
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


def run(batch: int, dry_run: bool, delay: float):
    session = SessionLocal()
    gcs = GCSClient()

    rows = session.execute(text("""
        SELECT id, title, company_name, description
        FROM jobsql
        WHERE description IS NOT NULL
          AND description NOT LIKE 'gs://%'
          AND description NOT LIKE '%??%'
        ORDER BY id
        LIMIT :batch
    """), {"batch": batch}).fetchall()

    if not rows:
        logger.info("No inline descriptions to migrate.")
        session.close()
        return

    logger.info(f"Found {len(rows)} jobs with inline descriptions{' (dry-run)' if dry_run else ''}")
    counts = {"ok": 0, "error": 0, "skipped": 0}

    for i, (job_id, title, company, description) in enumerate(rows, 1):
        if not description or not description.strip():
            counts["skipped"] += 1
            continue
        try:
            if dry_run:
                logger.info(f"  [{i}/{len(rows)}] Would upload: id={job_id} {title} @ {company} ({len(description)} chars)")
                counts["ok"] += 1
                continue

            uri = gcs.upload_description(company or "unknown", title or "unknown", job_id, description)
            session.execute(
                text("UPDATE jobsql SET description = :uri WHERE id = :id"),
                {"uri": uri, "id": job_id},
            )
            session.commit()
            counts["ok"] += 1
            logger.info(f"  [{i}/{len(rows)}] id={job_id} → {uri}")
        except Exception as e:
            session.rollback()
            counts["error"] += 1
            logger.error(f"  [{i}/{len(rows)}] id={job_id} failed: {e}")

        time.sleep(delay)

    session.close()
    logger.info("=" * 50)
    logger.info(f"  Migrated : {counts['ok']}")
    logger.info(f"  Skipped  : {counts['skipped']}")
    logger.info(f"  Errors   : {counts['error']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate inline descriptions to GCS")
    parser.add_argument("--batch", type=int, default=1000, help="Max rows to process (default: 1000)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--delay", type=float, default=0.05, help="Seconds between uploads (default: 0.05)")
    args = parser.parse_args()
    run(batch=args.batch, dry_run=args.dry_run, delay=args.delay)
