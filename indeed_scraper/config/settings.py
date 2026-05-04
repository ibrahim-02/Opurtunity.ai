"""
Indeed-scraper-specific configuration.
Shared config (DB, GCS, Vertex) lives in the repo-root config/settings.py.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # indeed_scraper/
load_dotenv(BASE_DIR.parent / ".env")               # repo-root .env

# ── Delays ────────────────────────────────────────────────────────────────────
MIN_DELAY = int(os.getenv("MIN_DELAY", "3"))
MAX_DELAY = int(os.getenv("MAX_DELAY", "8"))

# ── Indeed-specific ───────────────────────────────────────────────────────────
# Days back for date filter: 1=24h, 3=3 days, 7=week, 14=2 weeks
DAYS_BACK = int(os.getenv("INDEED_DAYS_BACK", "1"))
LOCATION = os.getenv("INDEED_LOCATION", "United States")
MAX_PAGES_PER_QUERY = int(os.getenv("INDEED_MAX_PAGES", "5"))
FETCH_DESCRIPTIONS = os.getenv("INDEED_FETCH_DESCRIPTIONS", "true").lower() == "true"

# ── Search queries ─────────────────────────────────────────────────────────────
SEARCH_QUERIES = [
    "Data Analyst", "Business Analyst Data", "Analytics Analyst",
    "Reporting Analyst", "Marketing Data Analyst", "Financial Data Analyst",
    "Operations Analyst Data", "Insights Analyst",
    "Data Engineer", "Cloud Data Engineer", "Big Data Engineer",
    "Data Pipeline Engineer", "ETL Developer", "Database Engineer",
    "Data Platform Engineer", "Analytics Engineer",
    "Data Scientist", "Applied Scientist", "Research Scientist Machine Learning",
    "Quantitative Analyst", "Statistician Data",
    "Machine Learning Engineer", "ML Engineer", "AI Engineer",
    "Deep Learning Engineer", "NLP Engineer", "Computer Vision Engineer",
    "MLOps Engineer", "DevOps Engineer Data", "DataOps Engineer",
    "Business Intelligence Analyst", "BI Developer", "BI Analyst",
    "Power BI Developer", "Tableau Developer", "Looker Developer",
    "LLM Engineer", "Generative AI Engineer", "RAG Engineer",
    "Prompt Engineer", "AI Developer LLM",
    "Data Architect", "Solution Architect Data",
    "SQL Developer", "Python Developer Data",
]

# Optional JSON override: indeed_scraper/config/search_terms.json
_terms_file = BASE_DIR / "config" / "search_terms.json"
if _terms_file.exists():
    _custom = json.loads(_terms_file.read_text(encoding="utf-8"))
    SEARCH_QUERIES = _custom.get("queries", SEARCH_QUERIES)

# ── Company blocklist ─────────────────────────────────────────────────────────
EXCLUDED_COMPANIES = {
    "DataAnnotation", "Jobs Ai", "dice", "remote hunter", "jobright", "jobright.ai",
    "joveo AI", "Sundayy", "Joveo Ai", "jobs via equest", "lensa", "talent.com",
    "adzuna", "jooble", "zippia", "nexxt", "jobcase", "talentify", "jobot", "hired",
    "jobs via jobright", "recruit.net", "resume-library", "jora",
    "fetch recruit", "built in", "glassdoor", "ziprecruiter",
    "snagajob", "careerbuilder", "monster", "simplyhired", "the ladders",
    "the muse", "wellfound", "lever", "greenhouse", "smartrecruiters",
    "breezy hr", "jobvite", "workable", "betterteam", "jobscore",
    "recruitee", "teamtailor", "pinpoint", "freshteam", "zoho recruit",
    "robert half", "robert half technology", "randstad", "randstad digital",
    "randstad usa", "adecco", "manpower", "manpowergroup", "kelly services",
    "kelly", "kforce", "insight global", "aerotek", "experis", "apex systems",
    "teksystems", "hays", "beacon hill", "addison group", "cybercoders",
    "yoh services", "modis", "volt", "motion recruitment", "judge group",
    "mindlance", "mastech", "mastech digital", "vaco", "horizontal talent",
    "softpath system", "disys", "strategic staffing solutions", "staffmark",
    "staffing solutions", "recruiting solutions", "talent bridge",
    "net2source", "tti", "tanisha systems", "igate", "tek systems",
    "compunnel", "suna solutions", "lancesoft", "nityo infotech",
    "idexcel", "cynet systems", "futran solutions", "amerit consulting",
    "pyramid consulting", "axelon services", "iconma", "mvp staffing",
}

# ── Title allowlist ───────────────────────────────────────────────────────────
TITLE_KEYWORDS = [
    "analyst", "engineer", "scientist", "developer", "architect",
    "mlops", "devops", "dataops", "machine learning", "data", "bi ",
    " bi", "business intelligence", "analytics", "etl", "sql",
    "python", "cloud", "database", "pipeline", " ai ", "artificial intelligence",
    "llm", "nlp", "rag", "generative", "quantitative", "research scientist",
    "platform", "big data", "deep learning", "modeling", "visualization",
    "reporting", "tableau", "looker", "spark", "hadoop", "databricks",
    "snowflake", "dbt",
]
