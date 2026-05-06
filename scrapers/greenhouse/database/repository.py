"""
Greenhouse job repository — thin wrapper over BaseJobRepository.
Adds the Greenhouse-specific CompanyRepository for tracking discovered boards.
GCS upload is now inherited from BaseJobRepository — descriptions go to gs://.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.db_models import GreenhouseCompany
from scrapers.repository import BaseJobRepository


class JobRepository(BaseJobRepository):
    SOURCE = "greenhouse"


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
