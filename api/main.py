"""
Job search API.

Run locally:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    POST /api/search
    POST /api/match-resume
    GET  /api/skills/popular
    GET  /health
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.deps import lifespan, limiter
from api.routes import search, resume, skills, ask, explain

app = FastAPI(title="Job Search API", version="1.0.0", lifespan=lifespan)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow Vercel frontend + localhost dev
_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(search.router, prefix="/api")
app.include_router(resume.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(explain.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
