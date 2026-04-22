from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from loguru import logger

import config.settings as _cfg
from models.db_models import JobSQL, ScrapeLog
from models.pydantic_models import JobExtracted


def _is_excluded_company(company_name: str | None) -> bool:
    if not company_name:
        return False
    name_lower = company_name.lower().strip()
    name_nospace = name_lower.replace(" ", "")
    return any(
        blocked.lower() in name_lower or blocked.lower().replace(" ", "") in name_nospace
        for blocked in _cfg.EXCLUDED_COMPANIES
    )


def _has_valid_title(title: str | None) -> bool:
    if not title:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in _cfg.TITLE_KEYWORDS)


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_job(self, job: JobExtracted) -> str:
        """
        Insert a job into the database after applying filters.
        Returns:
          'inserted'  — new job inserted
          'duplicate' — link already exists (DB unique constraint)
          'blocked'   — filtered out by company blocklist
          'bad_title' — filtered out by title allowlist
        """
        if _is_excluded_company(job.company_name):
            logger.debug(f"Blocked company: '{job.company_name}' — {job.title}")
            return "blocked"

        if not _has_valid_title(job.title):
            logger.debug(f"Bad title filtered: '{job.title}' at '{job.company_name}'")
            return "bad_title"

        try:
            job_orm = JobSQL(
                company_name=job.company_name,
                title=job.title,
                description=job.description,
                link=job.link,
                location=job.location,
                posted_date=datetime.now(timezone.utc),
                salary=job.salary.model_dump() if job.salary else None,
            )
            self.session.add(job_orm)
            self.session.commit()
            logger.info(f"Inserted: '{job.title}' @ '{job.company_name}'")
            return "inserted"
        except IntegrityError as e:
            self.session.rollback()
            # Only count as duplicate when it's a unique-constraint violation.
            # Other IntegrityErrors (e.g. NOT NULL) must surface as errors so
            # they don't silently swallow every insert.
            orig = str(e.orig).lower()
            if "unique" in orig or "duplicate key" in orig:
                logger.debug(f"Duplicate skipped: {job.link}")
                return "duplicate"
            logger.error(f"Insert failed for '{job.title}' @ '{job.company_name}': {e.orig}")
            return "error"

    def bulk_insert(self, jobs: list[JobExtracted]) -> dict:
        counts = {"inserted": 0, "duplicate": 0, "blocked": 0, "bad_title": 0, "error": 0}
        for job in jobs:
            try:
                result = self.insert_job(job)
                counts[result] += 1
            except Exception as e:
                logger.error(f"DB error for '{job.title}': {e}")
                self.session.rollback()
                counts["error"] += 1
        return counts

    def get_job_count(self) -> int:
        return self.session.query(JobSQL).count()

    def log_keyword_done(self, keyword: str, counts: dict) -> None:
        """Insert one ScrapeLog row summarising a completed search keyword."""
        total_in_db = self.get_job_count()
        record = ScrapeLog(
            keyword=keyword,
            cards_scraped=counts.get("scraped", 0),
            inserted=counts.get("inserted", 0),
            duplicate=counts.get("duplicate", 0),
            blocked=counts.get("blocked", 0),
            bad_title=counts.get("bad_title", 0),
            error=counts.get("error", 0),
            total_in_db=total_in_db,
        )
        self.session.add(record)
        self.session.commit()
        logger.info(
            f"  DB log → keyword='{keyword}' | "
            f"scraped={counts.get('scraped', 0)} | "
            f"inserted={counts.get('inserted', 0)} | "
            f"dupes={counts.get('duplicate', 0)} | "
            f"blocked={counts.get('blocked', 0)} | "
            f"filtered={counts.get('bad_title', 0)} | "
            f"total_in_db={total_in_db}"
        )
