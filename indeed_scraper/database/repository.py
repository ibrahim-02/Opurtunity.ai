from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import indeed_scraper.config.settings as _cfg
from models.db_models import JobSQL, ScrapeLog


def _is_excluded_company(name: str | None) -> bool:
    if not name:
        return False
    n = name.lower().strip()
    n_nospace = n.replace(" ", "")
    return any(
        b.lower() in n or b.lower().replace(" ", "") in n_nospace
        for b in _cfg.EXCLUDED_COMPANIES
    )


def _has_valid_title(title: str | None) -> bool:
    if not title:
        return False
    return any(kw in title.lower() for kw in _cfg.TITLE_KEYWORDS)


class JobRepository:
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
        source: str = "indeed",
    ) -> str:
        """
        Returns 'inserted', 'duplicate', 'blocked', 'bad_title', or 'error'.
        """
        if _is_excluded_company(company_name):
            logger.debug("Blocked company: '{}' — {}", company_name, title)
            return "blocked"

        if not _has_valid_title(title):
            logger.debug("Bad title: '{}' @ '{}'", title, company_name)
            return "bad_title"

        try:
            job = JobSQL(
                company_name=company_name,
                title=title,
                description=description,
                link=link,
                location=location,
                posted_date=posted_date or datetime.now(timezone.utc),
                salary=salary,
                source=source,
            )
            self.session.add(job)
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

    def get_job_count(self) -> int:
        return self.session.query(JobSQL).count()

    def log_keyword_done(self, keyword: str, counts: dict) -> None:
        total = self.get_job_count()
        record = ScrapeLog(
            keyword=keyword,
            cards_scraped=counts.get("scraped", 0),
            inserted=counts.get("inserted", 0),
            duplicate=counts.get("duplicate", 0),
            blocked=counts.get("blocked", 0),
            bad_title=counts.get("bad_title", 0),
            error=counts.get("error", 0),
            total_in_db=total,
        )
        self.session.add(record)
        self.session.commit()
        logger.info(
            "DB log → '{}' | scraped={} inserted={} dupes={} blocked={} filtered={} total={}",
            keyword,
            counts.get("scraped", 0),
            counts.get("inserted", 0),
            counts.get("duplicate", 0),
            counts.get("blocked", 0),
            counts.get("bad_title", 0),
            total,
        )
