from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SalaryInfo(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = "USD"


class JobExtracted(BaseModel):
    company_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    link: str
    location: Optional[str] = None
    posted_date: Optional[datetime] = None
    salary: Optional[SalaryInfo] = None
