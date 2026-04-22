from sqlalchemy import Column, Integer, String, TIMESTAMP, JSON, Index, func
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

    __table_args__ = (
        Index("idx_jobsql_link", "link"),
        Index("idx_jobsql_posted_date", "posted_date"),
    )

    def __repr__(self):
        return f"<JobSQL(id={self.id}, title='{self.title}', company='{self.company_name}')>"


class ScrapeLog(Base):
    """One row written to the DB after every search-keyword completes."""
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
