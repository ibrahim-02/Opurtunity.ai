"""
Backfill experience_years for jobs where it is currently NULL.

Pass 1 (free):  deterministic regex — catches "5+ years of experience", "3-5 years", etc.
Pass 2 (LLM):   Gemini call for rows regex couldn't resolve — catches natural-language
                phrasings like "a decade of experience", "at least four years", etc.

Safe to re-run: only updates rows where experience_years IS NULL and a value is found.

Usage (from repo root):
    python -m pipeline.backfill_years
    python -m pipeline.backfill_years --source linkedin
    python -m pipeline.backfill_years --batch 1500
    python -m pipeline.backfill_years --regex-only   # skip LLM pass
"""
import argparse
import json
import re
import sys
import time

from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal
from llm.factory import get_llm_client
from llm.prompts import YEARS_EXTRACTION_PROMPT
from llm.section_parser import _strip_html
from llm.skill_extractor import _extract_years_fallback
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
            SELECT id, description
            FROM jobsql
            WHERE experience_years IS NULL
              AND description IS NOT NULL
              AND description NOT LIKE '%??%'
              AND source = :source
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch, "source": source}).fetchall()
    else:
        q = text("""
            SELECT id, description
            FROM jobsql
            WHERE experience_years IS NULL
              AND description IS NOT NULL
              AND description NOT LIKE '%??%'
            ORDER BY id
            LIMIT :batch
        """)
        return session.execute(q, {"batch": batch}).fetchall()


def _resolve_text(description: str, gcs: GCSClient) -> str | None:
    if description.startswith("gs://"):
        raw = gcs.download_description(description)
        if not raw:
            return None
    else:
        raw = description
    cleaned = _strip_html(raw)
    return cleaned if cleaned.strip() else None


def _llm_extract_years(text_content: str, client) -> int | None:
    prompt = YEARS_EXTRACTION_PROMPT.format(description=text_content[:4000])
    try:
        raw = client.generate(prompt)
        # strip markdown fences if present
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(raw)
        val = parsed.get("experience_years")
        if isinstance(val, int) and 0 <= val <= 40:
            return val
        if isinstance(val, float) and 0 <= val <= 40:
            return int(val)
        if isinstance(val, str):
            m = re.search(r"\d+", val)
            if m:
                return int(m.group())
    except Exception as e:
        logger.debug(f"LLM years parse failed: {e}")
    return None


def run(batch: int, source: str | None, regex_only: bool, delay: float):
    session = SessionLocal()
    gcs = GCSClient()

    rows = fetch_pending(session, batch, source)
    if not rows:
        logger.info("No jobs with null experience_years found.")
        session.close()
        return

    logger.info(f"Found {len(rows)} jobs with experience_years=NULL")

    llm_client = None
    if not regex_only:
        logger.info("Initializing LLM client for pass 2...")
        llm_client = get_llm_client()
        if not llm_client.is_available():
            logger.warning("LLM client unavailable — running regex-only pass")
            llm_client = None

    counts = {"regex": 0, "llm": 0, "null": 0, "skip": 0}

    for i, (job_id, description) in enumerate(rows, 1):
        text_content = _resolve_text(description, gcs)
        if not text_content:
            counts["skip"] += 1
            continue

        # Pass 1: regex (free, instant)
        years = _extract_years_fallback(text_content)
        if years is not None:
            counts["regex"] += 1
        elif llm_client:
            # Pass 2: LLM
            years = _llm_extract_years(text_content, llm_client)
            if years is not None:
                counts["llm"] += 1
                logger.info(f"  [{i}/{len(rows)}] id={job_id} → LLM found {years} years")
            else:
                counts["null"] += 1
        else:
            counts["null"] += 1

        if years is not None:
            session.execute(
                text("UPDATE jobsql SET experience_years = :years WHERE id = :id"),
                {"years": years, "id": job_id},
            )

        # Commit every 50 rows to avoid large transactions
        if i % 50 == 0:
            session.commit()
            logger.info(
                f"  Progress {i}/{len(rows)} — "
                f"regex={counts['regex']} llm={counts['llm']} null={counts['null']}"
            )

        if llm_client and years is not None:
            time.sleep(delay)

    session.commit()
    session.close()

    logger.info("=" * 50)
    logger.info(f"  Regex filled : {counts['regex']}")
    logger.info(f"  LLM filled   : {counts['llm']}")
    logger.info(f"  Still null   : {counts['null']}")
    logger.info(f"  Skipped      : {counts['skip']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill experience_years via regex + LLM")
    parser.add_argument("--batch", type=int, default=2000, help="Max rows (default: 2000)")
    parser.add_argument("--source", type=str, default=None, help="linkedin | greenhouse")
    parser.add_argument("--regex-only", action="store_true", help="Skip LLM pass")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between LLM calls (default: 0.3)")
    args = parser.parse_args()
    run(batch=args.batch, source=args.source, regex_only=args.regex_only, delay=args.delay)
