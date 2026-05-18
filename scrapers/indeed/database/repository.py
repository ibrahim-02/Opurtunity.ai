"""
Indeed job repository — thin wrapper over BaseJobRepository.
Adds Indeed's per-keyword ScrapeLog writer.
"""
from loguru import logger

from models.db_models import ScrapeLog
from scrapers.repository import BaseJobRepository


class JobRepository(BaseJobRepository):
    SOURCE = "indeed"

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
            "DB log → '{}' | scraped={} inserted={} dupes={} blocked={} filtered={} non_us={} total={}",
            keyword,
            counts.get("scraped", 0),
            counts.get("inserted", 0),
            counts.get("duplicate", 0),
            counts.get("blocked", 0),
            counts.get("bad_title", 0),
            counts.get("non_us", 0),
            total,
        )
