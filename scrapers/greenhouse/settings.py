"""
Greenhouse-scraper-specific configuration.
Shared config (DB, GCS, Ollama, embeddings) lives in the repo-root config/settings.py.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # scrapers.greenhouse/
load_dotenv(BASE_DIR.parent / ".env")               # repo-root .env

SEC_COMPANIES_TABLE = "public.sec_companies"

CONCURRENCY = int(os.getenv("CONCURRENCY", "20"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))

USA_LOCATION_TERMS = [
    "united states", "usa", "u.s.a", "u.s.", "america",
    "remote", "anywhere in the u", "work from home",
    ", al", ", ak", ", az", ", ar", ", ca", ", co", ", ct", ", de",
    ", fl", ", ga", ", hi", ", id", ", il", ", in", ", ia", ", ks",
    ", ky", ", la", ", me", ", md", ", ma", ", mi", ", mn", ", ms",
    ", mo", ", mt", ", ne", ", nv", ", nh", ", nj", ", nm", ", ny",
    ", nc", ", nd", ", oh", ", ok", ", or", ", pa", ", ri", ", sc",
    ", sd", ", tn", ", tx", ", ut", ", vt", ", va", ", wa", ", wv",
    ", wi", ", wy", ", dc",
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
]

TITLE_EXCLUDE_KEYWORDS = [
    "mechanical engineer", "mechanical engineering",
    "electrical engineer", "electrical engineering",
    "principal",
    "director",
    "staff ",
    "head of",
    " head,",
    "senior manager",
]

TITLE_KEYWORDS = [
    "analyst", "engineer", "scientist", "developer", "architect",
    "mlops", "devops", "dataops", "machine learning", "data", "bi ",
    " bi", "business intelligence", "analytics", "etl", "sql",
    "python", "cloud", "database", "pipeline", " ai ", "llm",
    "nlp", "rag", "generative", "quantitative", "research scientist",
    "platform", "big data", "deep learning", "modeling",
    "visualization", "reporting", "tableau", "looker", "spark",
    "databricks", "snowflake", "dbt",
]
