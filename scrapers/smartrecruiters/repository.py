"""SmartRecruiters job repository -- uses BaseJobRepository (gets GCS upload + filters for free)."""
from scrapers.repository import BaseJobRepository


class JobRepository(BaseJobRepository):
    SOURCE = "smartrecruiters"
