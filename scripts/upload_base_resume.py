"""
Upload base_resume.json to GCS so the tailoring pipeline can read it.

Usage (run from repo root):
    python -m scripts.upload_base_resume
    python -m scripts.upload_base_resume --path /custom/path/base_resume.json
"""
import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from storage.gcs_client import GCSClient

_DEFAULT_PATH = Path(__file__).parent.parent / "base_resume.json"

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)


def run(local_path: Path):
    if not local_path.exists():
        logger.error(f"File not found: {local_path}")
        sys.exit(1)

    try:
        data = json.loads(local_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {local_path}: {e}")
        sys.exit(1)

    name = data.get("name", "unknown")
    exp_count = len(data.get("experience") or [])
    proj_count = len(data.get("projects") or [])
    skill_count = len(data.get("skills") or [])
    logger.info(f"Loaded resume for '{name}' — {exp_count} roles, {proj_count} projects, {skill_count} skills")

    logger.info("Connecting to GCS...")
    gcs = GCSClient()

    blob = gcs._bucket.blob("base_resume.json")
    blob.upload_from_string(
        json.dumps(data, indent=2, ensure_ascii=True),
        content_type="application/json; charset=utf-8",
    )
    bucket = gcs._bucket.name
    logger.info(f"Uploaded → gs://{bucket}/base_resume.json")
    logger.info("Run pipeline/tailor_resumes.py to start tailoring jobs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload base_resume.json to GCS")
    parser.add_argument(
        "--path",
        type=Path,
        default=_DEFAULT_PATH,
        help=f"Path to base_resume.json (default: {_DEFAULT_PATH})",
    )
    args = parser.parse_args()
    run(args.path)
