import json
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Linked_job_scrapping")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

# Scraping delays
MIN_DELAY = int(os.getenv("MIN_DELAY", "3"))
MAX_DELAY = int(os.getenv("MAX_DELAY", "8"))
SCROLL_PAUSE = int(os.getenv("SCROLL_PAUSE", "2"))
MAX_SCROLLS = int(os.getenv("MAX_SCROLLS", "10"))

# LinkedIn
LINKEDIN_BASE_URL = "https://www.linkedin.com/jobs/search/"

# ── User-configurable scraper parameters ──────────────────────────────────────

# Time window: r86400=last 24h | r604800=last week | r2592000=last month
TIME_FILTER = os.getenv("TIME_FILTER", "r86400")

# Countries to search — LinkedIn location strings, comma-separated.
# Empty string means no location filter (global). Example: "United States,United Kingdom"
_countries_raw = os.getenv("SEARCH_COUNTRIES", "United States")
SEARCH_COUNTRIES: list[str] = (
    [c.strip() for c in _countries_raw.split(",") if c.strip()]
    if _countries_raw.strip()
    else [""]  # empty string = no location filter
)

# Jobs with >= this many applicants are skipped (set to 0 to disable filter)
MAX_APPLICANTS = int(os.getenv("MAX_APPLICANTS", "100"))

# Pages to fetch per keyword per country (25 jobs/page)
MAX_PAGES_PER_SKILL = int(os.getenv("MAX_PAGES_PER_SKILL", "12"))
MAX_RESULTS_PER_SKILL = MAX_PAGES_PER_SKILL * 25

# ── Skill-based search terms ───────────────────────────────────────────────────
TARGET_SKILLS = [
    "SQL",
    "Power BI",
    "ETL",
    "Data Visualization",
    "AWS",
    "Airflow",
    "Docker",
    "LLM",
    "Co-pilot",
    "RAG",
    "Web Scraping",
]

# ── Job-title-based search terms (catches naming variations) ───────────────────
SEARCH_QUERIES = [
    # Data Analyst family
    "Data Analyst",
    "Business Analyst Data",
    "Analytics Analyst",
    "Reporting Analyst",
    "Marketing Data Analyst",
    "Financial Data Analyst",
    "Operations Analyst Data",
    "Insights Analyst",
    # Data Engineer family
    "Data Engineer",
    "Cloud Data Engineer",
    "Big Data Engineer",
    "Data Pipeline Engineer",
    "ETL Developer",
    "Database Engineer",
    "Data Platform Engineer",
    "Analytics Engineer",
    # Data Scientist family
    "Data Scientist",
    "Applied Scientist",
    "Research Scientist Machine Learning",
    "Quantitative Analyst",
    "Statistician Data",
    # ML / AI Engineer family
    "Machine Learning Engineer",
    "ML Engineer",
    "AI Engineer",
    "Deep Learning Engineer",
    "NLP Engineer",
    "Computer Vision Engineer",
    "AI ML Engineer",
    # MLOps / DevOps family
    "MLOps Engineer",
    "DevOps Engineer Data",
    "DataOps Engineer",
    "Platform Engineer ML",
    # BI family
    "Business Intelligence Analyst",
    "BI Developer",
    "BI Analyst",
    "Power BI Developer",
    "Tableau Developer",
    "Looker Developer",
    # LLM / GenAI family
    "LLM Engineer",
    "Generative AI Engineer",
    "RAG Engineer",
    "Prompt Engineer",
    "AI Developer LLM",
    # Architecture
    "Data Architect",
    "Solution Architect Data",
    "SQL Developer",
    "Python Developer Data",
]

# ── Optional override: config/search_terms.json ───────────────────────────────
# Create this file to replace the default skill/query lists without editing code.
# Format: {"skills": ["SQL", "Python"], "queries": ["Data Analyst", "ML Engineer"]}
_terms_file = BASE_DIR / "config" / "search_terms.json"
if _terms_file.exists():
    _custom = json.loads(_terms_file.read_text(encoding="utf-8"))
    TARGET_SKILLS = _custom.get("skills", TARGET_SKILLS)
    SEARCH_QUERIES = _custom.get("queries", SEARCH_QUERIES)

# ── All queries combined for scraping ─────────────────────────────────────────
ALL_SEARCH_TERMS = TARGET_SKILLS + SEARCH_QUERIES

# ── Company blocklist (job portals + pure staffing/recruiting agencies) ────────
# Lowercase — matched via substring so "jobs via equest" catches "Jobs Via Equest"
EXCLUDED_COMPANIES = {
    # Job portals / aggregators
    "dice",
    "remote hunter",
    "jobright",
    "jobright.ai",
    "joveo AI",
    "Sundayy",
    "Joveo Ai",
    "jobs via jobright",
    "lensa",
    "talent.com",
    "adzuna",
    "jooble",
    "zippia",
    "nexxt",
    "jobcase",
    "talentify",
    "jobot",
    "hired",
    "jobs via equest",
    "recruit.net",
    "resume-library",
    "jora",
    "fetch recruit",
    "built in",
    "glassdoor",
    "indeed",
    "ziprecruiter",
    "snagajob",
    "careerbuilder",
    "monster",
    "simplyhired",
    "the ladders",
    "the muse",
    "wellfound",
    "lever",
    "greenhouse",
    "smartrecruiters",
    "breezy hr",
    "jobvite",
    "workable",
    "betterteam",
    "jobscore",
    "recruitee",
    "teamtailor",
    "pinpoint",
    "freshteam",
    "zoho recruit",
    # Pure staffing / recruiting agencies
    "robert half",
    "robert half technology",
    "randstad",
    "randstad digital",
    "randstad usa",
    "adecco",
    "manpower",
    "manpowergroup",
    "kelly services",
    "kelly",
    "kforce",
    "insight global",
    "aerotek",
    "experis",
    "apex systems",
    "teksystems",
    "hays",
    "RemoteHunter",
    "Remote Hunter",
    "Jobs via Dice",
    "jobs via lensa",
    "jobs via talent.com",
    "jobs via adzuna",
    "jobs via jooble",
    "hackajob",
    "Dice",
    "beacon hill",
    "addison group",
    "cybercoders",
    "yoh services",
    "modis",
    "volt",
    "motion recruitment",
    "judge group",
    "mindlance",
    "mastech",
    "mastech digital",
    "vaco",
    "horizontal talent",
    "softpath system",
    "disys",
    "strategic staffing solutions",
    "staffmark",
    "staffing solutions",
    "recruiting solutions",
    "talent bridge",
    "staffing bridge",
    "staffing inc",
    "staffing llc",
    "staffing group",
    "recruiting group",
    "hiring group",
    "talent group",
    "workforce solutions",
    "workforce staffing",
    "net2source",
    "tti",
    "tanisha systems",
    "igate",
    "tek systems",
    "compunnel",
    "suna solutions",
    "lancesoft",
    "nityo infotech",
    "idexcel",
    "doit software",
    "cynet systems",
    "futran solutions",
    "amerit consulting",
    "inforeliance",
    "steneral consulting",
    "pyramid consulting",
    "infotree global solutions",
    "axelon services",
    "iconma",
    "mvp staffing",
}

# ── Title keyword allowlist ────────────────────────────────────────────────────
# A job is kept only if its title contains at least one of these (case-insensitive)
TITLE_KEYWORDS = [
    "analyst",
    "engineer",
    "scientist",
    "developer",
    "architect",
    "mlops",
    "devops",
    "dataops",
    "machine learning",
    "data",
    "bi ",
    " bi",
    "business intelligence",
    "analytics",
    "etl",
    "sql",
    "python",
    "cloud",
    "database",
    "pipeline",
    " ai ",
    "artificial intelligence",
    "llm",
    "nlp",
    "rag",
    "generative",
    "quantitative",
    "research scientist",
    "platform",
    "big data",
    "deep learning",
    "modeling",
    "visualization",
    "reporting",
    "tableau",
    "looker",
    "spark",
    "hadoop",
    "databricks",
    "snowflake",
    "dbt",
]
