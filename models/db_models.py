from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, TIMESTAMP, JSON, Boolean, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobSQL(Base):
    __tablename__ = "jobsql"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    link = Column(String, nullable=False, unique=True)
    location = Column(String, nullable=True)
    posted_date = Column(TIMESTAMP, nullable=True)
    salary = Column(JSON, nullable=True)
    source = Column(String, nullable=True, default="linkedin")
    skills_extracted = Column(JSONB, nullable=True)
    experience_years = Column(Integer, nullable=True)
    enriched_at = Column(TIMESTAMP, nullable=True)
    embedding = Column(Vector(768), nullable=True)
    added_at = Column(Integer, server_default=func.cast(func.extract("epoch", func.now()) / 3600, Integer), nullable=False)
    tailored_resume_uri = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_jobsql_link", "link"),
        Index("idx_jobsql_posted_date", "posted_date"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<JobSQL(id={self.id}, title='{self.title}', company='{self.company_name}')>"


class ScrapeLog(Base):
    """One row written after every search-keyword scrape completes."""
    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String, nullable=False)
    cards_scraped = Column(Integer, default=0)
    inserted = Column(Integer, default=0)
    duplicate = Column(Integer, default=0)
    blocked = Column(Integer, default=0)
    bad_title = Column(Integer, default=0)
    error = Column(Integer, default=0)
    total_in_db = Column(Integer, default=0)
    completed_at = Column(TIMESTAMP, server_default=func.now())

    def __repr__(self):
        return (
            f"<ScrapeLog(keyword='{self.keyword}', inserted={self.inserted}, "
            f"total_in_db={self.total_in_db})>"
        )


class GreenhouseCompany(Base):
    """Cache of companies confirmed to have a Greenhouse jobs board."""
    __tablename__ = "greenhouse_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String)
    slug = Column(String, unique=True)
    job_count = Column(Integer, default=0)
    last_scraped = Column(TIMESTAMP)
    active = Column(Boolean, default=True)
    discovered_at = Column(TIMESTAMP, server_default=func.now())


class WorkdayCompany(Base):
    """Cache of companies confirmed to have a Workday jobs board."""
    __tablename__ = "workday_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String)
    tenant = Column(String, unique=True)   # subdomain slug, e.g. "salesforce"
    wd_num = Column(Integer)               # server number 1–5
    career_site = Column(String)           # path segment, e.g. "External_Careers"
    job_count = Column(Integer, default=0)
    last_scraped = Column(TIMESTAMP)
    active = Column(Boolean, default=True)
    discovered_at = Column(TIMESTAMP, server_default=func.now())
