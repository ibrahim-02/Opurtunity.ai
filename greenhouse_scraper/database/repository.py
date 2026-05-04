from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from loguru import logger

import greenhouse_scraper.config.settings as _cfg
from models.db_models import JobSQL, GreenhouseCompany


def _has_valid_title(title: str | None) -> bool:
    if not title:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in _cfg.TITLE_KEYWORDS)


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_job(
        self,
        *,
        company_name: str,
        title: str,
        description: str | None,
        link: str,
        location: str | None,
        source: str = "greenhouse",
    ) -> str:
        """Returns 'inserted', 'duplicate', or 'bad_title'."""
        if not _has_valid_title(title):
            logger.debug(f"Bad title filtered: '{title}' @ '{company_name}'")
            return "bad_title"

        try:
            job = JobSQL(
                company_name=company_name,
                title=title,
                description=description,
                link=link,
                location=location,
                posted_date=datetime.now(timezone.utc),
                source=source,
            )
            self.session.add(job)
            self.session.commit()
            logger.info(f"Inserted: '{title}' @ '{company_name}'")
            return "inserted"
        except IntegrityError:
            self.session.rollback()
            logger.debug(f"Duplicate skipped: {link}")
            return "duplicate"

    def get_job_count(self) -> int:
        return self.session.query(JobSQL).count()


class CompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_discovered(self, company_name: str, slug: str):
        existing = self.session.query(GreenhouseCompany).filter_by(slug=slug).first()
        if not existing:
            self.session.add(GreenhouseCompany(company_name=company_name, slug=slug))
            self.session.commit()

    def get_active_companies(self) -> list[GreenhouseCompany]:
        return self.session.query(GreenhouseCompany).filter_by(active=True).all()

    def update_scraped(self, slug: str, job_count: int):
        company = self.session.query(GreenhouseCompany).filter_by(slug=slug).first()
        if company:
            company.job_count = job_count
            company.last_scraped = datetime.now(timezone.utc)
            self.session.commit()

    def deactivate(self, slug: str):
        company = self.session.query(GreenhouseCompany).filter_by(slug=slug).first()
        if company:
            company.active = False
            self.session.commit()

    def get_company_count(self) -> int:
        return self.session.query(GreenhouseCompany).count()
