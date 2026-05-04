"""
Recover description-path corruption: for every jobsql row whose description
contains '???', look up the actual GCS file by extracting the job_id from the
filename suffix (_<id>.txt) and rewrite the path.

Run from repo root:
    python -u -m pipeline.recover_descriptions          # dry-run
    python -u -m pipeline.recover_descriptions --apply  # actually UPDATE
"""
import argparse
import re
import sys

from google.cloud import storage
from loguru import logger
from sqlalchemy import text

import config.settings as _cfg
from database.connection import SessionLocal

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

# Filenames look like:  descriptions/<Company>/<Title with stuff>_<job_id>.txt
_ID_FROM_NAME = re.compile(r"_(\d+)\.txt$")


def build_id_to_path_map(client: storage.Client, bucket_name: str) -> dict[int, str]:
    """List every blob under descriptions/ and map job_id -> gs:// URI."""
    bucket = client.bucket(bucket_name)
    id_map: dict[int, str] = {}
    duplicates = 0

    logger.info(f"Listing gs://{bucket_name}/descriptions/ ...")
    for blob in client.list_blobs(bucket, prefix="descriptions/"):
        m = _ID_FROM_NAME.search(blob.name)
        if not m:
            continue
        job_id = int(m.group(1))
        uri = f"gs://{bucket_name}/{blob.name}"
        if job_id in id_map and id_map[job_id] != uri:
            duplicates += 1
        id_map[job_id] = uri

    logger.info(f"Indexed {len(id_map):,} unique job_ids from GCS ({duplicates} duplicate-id collisions)")
    return id_map


def run(apply_changes: bool):
    session = SessionLocal()

    # 1. Load broken rows
    rows = session.execute(text("""
        SELECT id, company_name, title, description
        FROM jobsql
        WHERE description LIKE '%???%'
    """)).fetchall()
    logger.info(f"Broken rows in DB: {len(rows):,}")

    if not rows:
        logger.info("Nothing to fix.")
        session.close()
        return

    # 2. Build id -> gs:// map from GCS
    gcs_client = storage.Client.from_service_account_json(_cfg.GCS_KEY_PATH)
    id_map = build_id_to_path_map(gcs_client, _cfg.GCS_BUCKET_NAME)

    # 3. Match each broken row by job_id
    matched = 0
    unmatched: list[int] = []
    updates: list[tuple[int, str]] = []
    for row in rows:
        new_path = id_map.get(row.id)
        if new_path:
            matched += 1
            updates.append((row.id, new_path))
        else:
            unmatched.append(row.id)

    logger.info(f"Matched: {matched:,} / {len(rows):,}  ({100*matched/len(rows):.1f}%)")
    logger.info(f"Unmatched (no GCS file with that _<id>.txt): {len(unmatched):,}")

    # show 3 sample matches so you can sanity-check
    for job_id, path in updates[:3]:
        logger.info(f"  sample: id={job_id}  ->  {path}")

    if not apply_changes:
        logger.info("DRY-RUN: no DB changes made. Re-run with --apply to commit.")
        session.close()
        return

    # 4. Apply updates in batches
    logger.info(f"Applying {len(updates):,} UPDATE statements...")
    BATCH = 500
    for i in range(0, len(updates), BATCH):
        chunk = updates[i:i + BATCH]
        for job_id, path in chunk:
            session.execute(
                text("UPDATE jobsql SET description = :path WHERE id = :id"),
                {"path": path, "id": job_id},
            )
        session.commit()
        logger.info(f"  committed {min(i+BATCH, len(updates)):,} / {len(updates):,}")

    logger.info("Done.")
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually UPDATE the DB (default is dry-run)")
    args = parser.parse_args()
    run(apply_changes=args.apply)
