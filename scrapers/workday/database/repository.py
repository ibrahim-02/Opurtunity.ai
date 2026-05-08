"""Workday repositories — job insertion via BaseJobRepository, company tracking."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.db_models import WorkdayCompany
from scrapers.repository import BaseJobRepository


class JobRepository(BaseJobRepository):
    SOURCE = "workday"


class CompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def known_tenants(self) -> set[str]:
        rows = self.session.query(WorkdayCompany.tenant).all()
        return {r[0] for r in rows if r[0]}

    def save(self, company_name: str, tenant: str, wd_num: int,
             career_site: str, job_count: int = 0):
        existing = self.session.query(WorkdayCompany).filter_by(tenant=tenant).first()
        if existing:
            # Update if career_site or wd_num changed
            existing.career_site = career_site
            existing.wd_num = wd_num
            existing.job_count = job_count
        else:
            self.session.add(WorkdayCompany(
                company_name=company_name,
                tenant=tenant,
                wd_num=wd_num,
                career_site=career_site,
                job_count=job_count,
            ))
        self.session.commit()

    def get_active(self) -> list[WorkdayCompany]:
        return self.session.query(WorkdayCompany).filter_by(active=True).all()

    def update_scraped(self, tenant: str, job_count: int):
        company = self.session.query(WorkdayCompany).filter_by(tenant=tenant).first()
        if company:
            company.job_count = job_count
            company.last_scraped = datetime.now(timezone.utc)
            self.session.commit()

    def deactivate(self, tenant: str):
        company = self.session.query(WorkdayCompany).filter_by(tenant=tenant).first()
        if company:
            company.active = False
            self.session.commit()
