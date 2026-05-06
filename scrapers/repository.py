"""
Shared job repository used by every scraper.

Handles:
  - Filter pipeline (blocked company → bad title → non-US → duplicate)
  - GCS upload of description text (gs:// URI stored in DB)
  - Inline-text fallback when GCS is unavailable
  - Counter dict that every caller can use uniformly

Per-scraper repositories should subclass this to add platform-specific helpers
(e.g. Greenhouse's CompanyRepository) rather than duplicating insert_job logic.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.db_models import JobSQL
from scrapers.filters import (
    is_excluded_company,
    is_us_location,
    passes_title,
)
from storage.gcs_client import GCSClient

_gcs: GCSClient | None = None


def _get_gcs() -> GCSClient | None:
    global _gcs
    if _gcs is None:
        try:
            _gcs = GCSClient()
        except Exception as e:
            logger.warning("GCS unavailable — descriptions stored inline: {}", e)
    return _gcs


class BaseJobRepository:
    """
    All scrapers go through this. Subclasses can add platform-specific methods
    but should not override insert_job.
    """

    SOURCE = "unknown"  # subclasses set this

    def __init__(self, session: Session):
        self.session = session

    def insert_job(
        self,
        *,
        title: str,
        company_name: str | None,
        description: str | None,
        link: str,
        location: str | None,
        posted_date: datetime | None = None,
        salary: dict | None = None,
        source: str | None = None,
    ) -> str:
        """
        Returns one of:
          'inserted', 'duplicate', 'blocked', 'bad_title', 'non_us', 'error'.
        Description text is uploaded to GCS; the gs:// URI is stored in the DB.
        Falls back to inline text if GCS is unavailable.
        """
        src = source or self.SOURCE

        if is_excluded_company(company_name):
            logger.info("  [blocked]   '{}' — {}", company_name, title)
            return "blocked"

        if not passes_title(title):
            logger.info("  [bad_title] '{}' @ '{}'", title, company_name)
            return "bad_title"

        if not is_us_location(location):
            logger.info("  [non_us]    '{}' @ '{}' ({})", title, company_name, location)
            return "non_us"

        try:
            gcs = _get_gcs()
            if gcs and description:
                try:
                    orm = JobSQL(
                        company_name=company_name,
                        title=title,
                        description=None,
                        link=link,
                        location=location,
                        posted_date=posted_date or datetime.now(timezone.utc),
                        salary=salary,
                        source=src,
                    )
                    self.session.add(orm)
                    self.session.flush()
                    gcs_uri = gcs.upload_description(
                        company_name or "unknown",
                        title,
                        orm.id,
                        description,
                    )
                    orm.description = gcs_uri
                    self.session.commit()
                    logger.info("Inserted: '{}' @ '{}' → {}", title, company_name, gcs_uri)
                    return "inserted"
                except IntegrityError as e:
                    self.session.rollback()
                    orig = str(e.orig).lower()
                    if "unique" in orig or "duplicate key" in orig:
                        logger.debug("Duplicate skipped: {}", link)
                        return "duplicate"
                    logger.error("Insert error for '{}': {}", title, e.orig)
                    return "error"
                except Exception as e:
                    self.session.rollback()
                    logger.warning("GCS upload failed, storing inline: {}", e)

            # Inline fallback
            orm = JobSQL(
                company_name=company_name,
                title=title,
                description=description,
                link=link,
                location=location,
                posted_date=posted_date or datetime.now(timezone.utc),
                salary=salary,
                source=src,
            )
            self.session.add(orm)
            self.session.commit()
            logger.info("Inserted: '{}' @ '{}'", title, company_name)
            return "inserted"

        except IntegrityError as e:
            self.session.rollback()
            orig = str(e.orig).lower()
            if "unique" in orig or "duplicate key" in orig:
                logger.debug("Duplicate skipped: {}", link)
                return "duplicate"
            logger.error("Insert error for '{}': {}", title, e.orig)
            return "error"

    def existing_links(self) -> set[str]:
        """All links already in the DB for this source — used for pre-fetch dedup."""
        rows = self.session.query(JobSQL.link).filter(JobSQL.source == self.SOURCE).all()
        return {r[0] for r in rows if r[0]}

    def get_job_count(self) -> int:
        return self.session.query(JobSQL).count()


def empty_counts() -> dict[str, int]:
    return {
        "scraped": 0, "inserted": 0, "duplicate": 0,
        "blocked": 0, "bad_title": 0, "non_us": 0, "error": 0,
    }
