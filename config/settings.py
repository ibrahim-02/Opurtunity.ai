"""
Shared configuration for all scrapers and the pipeline.
Values are read from environment variables (or the repo-root .env file).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # repo root: job_scrapper/
load_dotenv(BASE_DIR / ".env", override=True)

# Database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Linked_job_scrapping")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# LLM provider switch: "ollama" | "vertex"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# GCP / Cloud Storage
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "job-scraper-file")
GCS_KEY_PATH = os.getenv("GCS_KEY_PATH", str(BASE_DIR / "gcp-key.json"))

# Vertex AI
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
VERTEX_GEN_MODEL = os.getenv("VERTEX_GEN_MODEL", "gemini-2.5-flash")
VERTEX_EMBED_MODEL = os.getenv("VERTEX_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
