"""
Batch embedding pass — generates mxbai-embed-large vectors for job descriptions.

Usage (run from repo root: job_scrapper/):
    python -m pipeline.embed_jobs
    python -m pipeline.embed_jobs --batch 100
    python -m pipeline.embed_jobs --source greenhouse
"""
import argparse
import sys
import time

from loguru import logger
from sqlalchemy import text

import config.settings as _cfg
from database.connection import SessionLocal
from llm.factory import get_llm_client
from llm.section_parser import parse as parse_sections
from storage.gcs_client import GCSClient

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)


def fetch_pending(session, batch: int, source: str | None) -> list:
    # skip scrape-time encoding casualties (see enrich_jobs.py for context)
    if source:
        q = text("""
            SELECT id, title, company_name, description
            FROM jobsql
            WHERE description IS NOT NULL
              AND description NOT LIKE '%??%'
              AND embedding IS NULL
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
              AND description NOT LIKE '%??%'
              AND embedding IS NULL
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch}).fetchall()


def _vec_str(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


def run(batch: int, source: str | None, delay: float):
    logger.info("Connecting to database...")
    session = SessionLocal()

    logger.info("Connecting to GCS...")
    gcs = GCSClient()

    logger.info("Initializing LLM client...")
    client = get_llm_client()
    if not client.is_available():
        logger.error("LLM client not available — check provider config (LLM_PROVIDER, credentials)")
        session.close()
        return

    logger.info("Fetching pending jobs...")
    rows = fetch_pending(session, batch, source)
    if not rows:
        logger.info("No jobs pending embedding.")
        session.close()
        return

    logger.info(f"Embedding {len(rows)} jobs with {_cfg.EMBED_MODEL} (source={source or 'all'})")
    counts = {"ok": 0, "error": 0}

    for i, (job_id, title, company, description) in enumerate(rows, 1):
        try:
            text_content = (
                gcs.download_description(description)
                if description and description.startswith("gs://")
                else description
            )
            if not text_content:
                counts["error"] += 1
                logger.warning(f"  [{i}/{len(rows)}] Could not get description — skipping")
                continue

            embed_text = parse_sections(text_content)
            if not embed_text or not embed_text.strip():
                counts["error"] += 1
                logger.warning(f"  [{i}/{len(rows)}] Empty after section-parse — skipping")
                continue

            vector = client.embed(embed_text)
            if vector is None:
                counts["error"] += 1
                logger.warning(f"  [{i}/{len(rows)}] Embedding failed (input chars={len(embed_text)}) — skipping")
                continue

            session.execute(
                text("UPDATE jobsql SET embedding = CAST(:vec AS vector) WHERE id = :id"),
                {"vec": _vec_str(vector), "id": job_id},
            )
            session.commit()
            counts["ok"] += 1
            logger.info(f"  [{i}/{len(rows)}] {title} @ {company} → dim={len(vector)}")

        except Exception as e:
            session.rollback()
            counts["error"] += 1
            logger.error(f"  [{i}/{len(rows)}] id={job_id} failed: {e}")

        time.sleep(delay)

    session.close()
    client.close()

    logger.info("=" * 50)
    logger.info(f"  Embedded : {counts['ok']}")
    logger.info(f"  Errors   : {counts['error']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed job descriptions with mxbai-embed-large")
    parser.add_argument("--batch", type=int, default=50, help="Max jobs to embed (default: 50)")
    parser.add_argument("--source", type=str, default=None, help="Filter by source: linkedin | greenhouse")
    parser.add_argument("--delay", type=float, default=0.05, help="Seconds between embeddings (default: 0.05)")
    args = parser.parse_args()
    run(batch=args.batch, source=args.source, delay=args.delay)
