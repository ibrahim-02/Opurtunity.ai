"""
Batch skill extraction enrichment pass.

Usage (run from repo root: job_scrapper/):
    python -m pipeline.enrich_jobs
    python -m pipeline.enrich_jobs --batch 100
    python -m pipeline.enrich_jobs --source greenhouse
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal
from llm.ollama_client import OllamaClient
from llm.skill_extractor import SkillExtractor
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
            SELECT id, title, company_name, description
            FROM jobsql
            WHERE description IS NOT NULL
              AND skills_extracted IS NULL
              AND source = :source
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch, "source": source}).fetchall()
    else:
        q = text("""
            SELECT id, title, company_name, description
            FROM jobsql
            WHERE description IS NOT NULL
              AND skills_extracted IS NULL
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch}).fetchall()


def _get_description_text(description: str, gcs: GCSClient) -> str | None:
    """Return plain text — downloads from GCS if description is a gs:// URI."""
    if description and description.startswith("gs://"):
        return gcs.download_description(description)
    return description


def run(batch: int, source: str | None, delay: float):
    logger.info("Connecting to database...")
    session = SessionLocal()

    logger.info("Connecting to GCS...")
    gcs = GCSClient()

    logger.info("Checking Ollama...")
    client = OllamaClient()
    if not client.is_available():
        logger.error("Ollama is not running — start it with: ollama serve")
        session.close()
        return

    logger.info("Fetching pending jobs...")
    rows = fetch_pending(session, batch, source)
    if not rows:
        logger.info("No jobs pending enrichment.")
        session.close()
        return

    logger.info(f"Found {len(rows)} jobs to enrich (source={source or 'all'})")

    extractor = SkillExtractor(client)
    counts = {"ok": 0, "empty": 0, "error": 0}

    for i, (job_id, title, company, description) in enumerate(rows, 1):
        try:
            logger.info(f"  [{i}/{len(rows)}] {title} @ {company}")
            text_content = _get_description_text(description, gcs)
            if not text_content:
                counts["error"] += 1
                logger.warning(f"  [{i}/{len(rows)}] Could not get description text — skipping")
                continue
            skills = extractor.extract(text_content, company_name=company)

            if skills is not None:
                session.execute(
                    text("""
                        UPDATE jobsql
                        SET skills_extracted = :skills,
                            enriched_at      = :now
                        WHERE id = :id
                    """),
                    {
                        "skills": json.dumps({"skills": skills}),
                        "now": datetime.now(timezone.utc),
                        "id": job_id,
                    },
                )
                session.commit()
                if skills:
                    counts["ok"] += 1
                    logger.info(f"  [{i}/{len(rows)}] Done → {len(skills)} skills: {skills[:5]}")
                else:
                    counts["empty"] += 1
                    logger.info(f"  [{i}/{len(rows)}] Done → no technical skills in this job")
            else:
                counts["error"] += 1
                logger.warning(f"  [{i}/{len(rows)}] LLM returned unparseable response")

        except Exception as e:
            session.rollback()
            counts["error"] += 1
            logger.error(f"  [{i}/{len(rows)}] id={job_id} failed: {e}")

        time.sleep(delay)

    session.close()
    client.close()

    logger.info("=" * 50)
    logger.info(f"  Enriched : {counts['ok']}")
    logger.info(f"  Empty    : {counts['empty']}")
    logger.info(f"  Errors   : {counts['error']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM skill extraction enrichment pass")
    parser.add_argument("--batch", type=int, default=50, help="Max jobs to process (default: 50)")
    parser.add_argument("--source", type=str, default=None, help="Filter by source: linkedin | greenhouse")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between LLM calls (default: 0.5)")
    args = parser.parse_args()
    run(batch=args.batch, source=args.source, delay=args.delay)
