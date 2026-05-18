"""
LinkedIn job repository — thin wrapper over BaseJobRepository.
Adds the LinkedIn-specific scrape_log writer and the JobExtracted bridge.
"""
from datetime import datetime, timezone

from loguru import logger

from models.db_models import ScrapeLog
from models.pydantic_models import JobExtracted
from scrapers.repository import BaseJobRepository


class JobRepository(BaseJobRepository):
    SOURCE = "linkedin"

    def insert_extracted(self, job: JobExtracted) -> str:
        """Adapter: takes the LinkedIn JobExtracted pydantic model and inserts it."""
        return self.insert_job(
            title=job.title,
            company_name=job.company_name,
            description=job.description,
            link=job.link,
            location=job.location,
            posted_date=datetime.now(timezone.utc),
            salary=job.salary.model_dump() if job.salary else None,
            linkedin_followers=job.linkedin_followers,
            linkedin_employees=job.linkedin_employees,
        )

    # Old name used by main.py — alias to insert_extracted
    def insert_job_from_extracted(self, job: JobExtracted) -> str:
        return self.insert_extracted(job)

    def bulk_insert(self, jobs: list[JobExtracted]) -> dict:
        counts = {"inserted": 0, "duplicate": 0, "blocked": 0,
                  "bad_title": 0, "non_us": 0, "error": 0}
        for job in jobs:
            try:
                result = self.insert_extracted(job)
                counts[result] = counts.get(result, 0) + 1
            except Exception as e:
                logger.error(f"DB error for '{job.title}': {e}")
                self.session.rollback()
                counts["error"] += 1
        return counts

    def existing_linkedin_links(self) -> set[str]:
        """Backward-compat alias — same as existing_links() from base."""
        return self.existing_links()

    def log_keyword_done(self, keyword: str, counts: dict) -> None:
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
            f"non_us={counts.get('non_us', 0)} | "
            f"total_in_db={total_in_db}"
        )
