from fastapi import FastAPI, BackgroundTasks
from loguru import logger

from database.connection import init_db, SessionLocal
from database.repository import JobRepository
from llm.ollama_client import OllamaClient

app = FastAPI(title="LinkedIn Job Scraper", version="1.0.0")


@app.on_event("startup")
def startup():
    logger.info("Initializing database tables...")
    init_db()


@app.get("/health")
def health_check():
    ollama = OllamaClient()
    ollama_ok = ollama.is_available()
    ollama.close()

    session = SessionLocal()
    try:
        db_ok = True
        job_count = JobRepository(session).get_job_count()
    except Exception:
        db_ok = False
        job_count = 0
    finally:
        session.close()

    return {
        "status": "ok" if (db_ok and ollama_ok) else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "ollama": "available" if ollama_ok else "unavailable",
        "total_jobs": job_count,
    }


@app.post("/scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    from main import run_pipeline

    def _run_with_error_logging():
        try:
            run_pipeline()
        except Exception as e:
            logger.exception(f"Pipeline crashed: {e}")

    background_tasks.add_task(_run_with_error_logging)
    return {"message": "Scraping pipeline started — watch the terminal for logs"}
