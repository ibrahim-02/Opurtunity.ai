"""
Resume parser — extracts skills, experience years, and a search summary
from a plain-text or PDF resume using Gemini.

Used by:
  - api/routes/resume.py  (POST /api/parse-resume)
  - rag/search.py CLI     (--resume flag)
"""
import io
import json
import re

from loguru import logger

_PARSE_PROMPT = """You are a resume parser. Extract the following from the resume below:

1. skills — list of technical skills, tools, programming languages, frameworks, databases,
   cloud platforms, and named software. Same rules as a job description extractor:
   - Only explicit items — no inference
   - No generic labels: "AI", "Machine Learning", "software", "development"
   - No soft skills, degrees, or seniority labels
2. experience_years — total years of professional work experience (integer), or null
3. summary — 2-3 sentences describing this candidate's profile for job matching purposes.
   Focus on: role/domain, tech stack, seniority. Used as a search query embedding.

Return ONLY valid JSON — no markdown, no commentary:
{{"skills": ["skill1", "skill2", ...], "experience_years": <int or null>, "summary": "..."}}

Resume:
{resume_text}
"""


def parse_resume_text(text: str, client) -> dict:
    """
    Parse a plain-text resume string.
    Returns: {"skills": [...], "experience_years": int|None, "summary": str}
    """
    prompt = _PARSE_PROMPT.format(resume_text=text[:6000])
    try:
        raw = client.generate(prompt)
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(raw)
        return {
            "skills": parsed.get("skills", []) if isinstance(parsed.get("skills"), list) else [],
            "experience_years": (
                int(parsed["experience_years"])
                if isinstance(parsed.get("experience_years"), (int, float))
                else None
            ),
            "summary": parsed.get("summary", ""),
        }
    except Exception as e:
        logger.error(f"Resume parse failed: {e}")
        return {"skills": [], "experience_years": None, "summary": text[:500]}


def parse_resume_pdf(pdf_bytes: bytes, client) -> dict:
    """
    Extract text from PDF bytes, then parse.
    Requires: pypdf (pip install pypdf)
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages_text).strip()
        if not text:
            return {"skills": [], "experience_years": None, "summary": ""}
        return parse_resume_text(text, client)
    except ImportError:
        logger.error("pypdf not installed — run: pip install pypdf")
        return {"skills": [], "experience_years": None, "summary": ""}
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return {"skills": [], "experience_years": None, "summary": ""}
