"""
Shared FastAPI dependencies — DB session, LLM client, rate limiter.
Client and session are created once per app startup and reused.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import Limiter
from slowapi.util import get_remote_address

from database.connection import SessionLocal
from llm.factory import get_llm_client

limiter = Limiter(key_func=get_remote_address)

_client = None
_session = None


def get_client():
    return _client


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = get_llm_client()
    yield
    if _client:
        _client.close()
