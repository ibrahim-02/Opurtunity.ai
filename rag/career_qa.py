"""
Grounded career Q&A over the jobsql DB.

Pipeline:
  1. LLM classifies the question into a category (skills/companies/roles/trends/off_topic)
  2. We run the matching SQL aggregation against jobsql
  3. LLM synthesizes a natural-language answer from question + data
  4. Off-topic → polite refusal, no DB hit
"""
import json
import re

from loguru import logger
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential


_CLASSIFY_PROMPT = """You are a router for a job-market Q&A system. The system can ONLY answer questions
that can be grounded in a database of recent US tech job postings (titles, companies, skills, experience years).

Classify the user's question into ONE of these categories:
- "skills_for_role": "what skills do I need for X" / "what's required for X" — needs role keyword
- "top_skills": "what are the most in-demand skills" / "trending skills"
- "top_companies": "which companies are hiring" / "biggest hirers"
- "role_overview": "what does an X engineer do" / "what is an X" — answerable from JD aggregations
- "skill_gap": "I know X, what should I learn next for Y" — needs current skills + target role
- "off_topic": anything not answerable from job listings (general life advice, opinions, current events,
   non-job questions, "how is the industry changing", coding help, etc.)

Also extract:
- "role": the role/title mentioned, or null (e.g. "data engineer", "ml engineer")
- "skills_known": list of skills the user mentions already having, or []

Output ONLY JSON:
{{"category": "...", "role": "...", "skills_known": [...]}}

Question: {question}
"""


_ANSWER_PROMPT = """You are a grounded career advisor for the US tech job market.
Answer the user's question using ONLY the data provided below. Be specific and cite numbers when relevant.
If the data doesn't fully answer the question, say what IS in the data and acknowledge the limit.
Keep the answer to 4-8 sentences. Plain text, no markdown.

User question: {question}

Data from {n_jobs} recent job postings:
{data}

Answer:"""


_OFF_TOPIC_REPLY = (
    "I can only answer questions grounded in our database of recent US tech job postings — "
    "things like which skills are in demand, who's hiring, or what specific roles require. "
    "Try rephrasing your question around those areas."
)


def _normalize_role(role: str) -> str:
    """Lowercase + strip common suffixes for SQL ILIKE match."""
    if not role:
        return ""
    r = role.lower().strip()
    r = re.sub(r"\b(role|position|job|engineer|engineering)$", "", r).strip()
    return r


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
def _llm_call(client, prompt: str) -> str:
    return client.generate(prompt)


def _classify(client, question: str) -> dict:
    try:
        raw = _llm_call(client, _CLASSIFY_PROMPT.format(question=question))
        parsed = json.loads(raw)
        return {
            "category": parsed.get("category", "off_topic"),
            "role": (parsed.get("role") or "").strip().lower(),
            "skills_known": parsed.get("skills_known") or [],
        }
    except Exception as e:
        logger.warning(f"Classification failed: {e}")
        return {"category": "off_topic", "role": "", "skills_known": []}


def _fetch_skills_for_role(session, role: str, limit: int = 25) -> list[dict]:
    """Top skills mentioned in JDs whose title matches `role`."""
    rows = session.execute(text("""
        SELECT skill, COUNT(*) AS cnt
        FROM jobsql,
             jsonb_array_elements_text(skills_extracted->'required_skills') AS skill
        WHERE skills_extracted IS NOT NULL
          AND title ILIKE :role
        GROUP BY skill
        ORDER BY cnt DESC
        LIMIT :limit
    """), {"role": f"%{role}%", "limit": limit}).fetchall()
    return [{"skill": r.skill, "count": r.cnt} for r in rows]


def _fetch_top_skills(session, limit: int = 30) -> list[dict]:
    rows = session.execute(text("""
        SELECT skill, COUNT(*) AS cnt
        FROM jobsql,
             jsonb_array_elements_text(skills_extracted->'required_skills') AS skill
        WHERE skills_extracted IS NOT NULL
        GROUP BY skill
        ORDER BY cnt DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    return [{"skill": r.skill, "count": r.cnt} for r in rows]


def _fetch_top_companies(session, role: str | None = None, limit: int = 25) -> list[dict]:
    if role:
        rows = session.execute(text("""
            SELECT company_name, COUNT(*) AS cnt
            FROM jobsql
            WHERE company_name IS NOT NULL
              AND title ILIKE :role
            GROUP BY company_name
            ORDER BY cnt DESC
            LIMIT :limit
        """), {"role": f"%{role}%", "limit": limit}).fetchall()
    else:
        rows = session.execute(text("""
            SELECT company_name, COUNT(*) AS cnt
            FROM jobsql
            WHERE company_name IS NOT NULL
            GROUP BY company_name
            ORDER BY cnt DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return [{"company": r.company_name, "count": r.cnt} for r in rows]


def _fetch_role_overview(session, role: str) -> dict:
    """Job count + top skills + sample titles + avg experience years for a role."""
    skills = _fetch_skills_for_role(session, role, limit=15)
    companies = _fetch_top_companies(session, role=role, limit=10)
    avg_years = session.execute(text("""
        SELECT AVG(experience_years)::FLOAT AS avg_years, COUNT(*) AS cnt
        FROM jobsql
        WHERE title ILIKE :role AND experience_years IS NOT NULL
    """), {"role": f"%{role}%"}).fetchone()
    return {
        "top_skills": skills,
        "top_companies": companies,
        "avg_experience_years": round(avg_years.avg_years or 0, 1),
        "matching_jobs": avg_years.cnt or 0,
    }


def _fetch_skill_gap(session, role: str, skills_known: list[str]) -> dict:
    """Compare top skills for the role vs what the user knows."""
    role_skills = _fetch_skills_for_role(session, role, limit=20)
    known_lower = {s.lower() for s in skills_known}
    missing = [s for s in role_skills if s["skill"].lower() not in known_lower]
    overlap = [s for s in role_skills if s["skill"].lower() in known_lower]
    return {
        "you_have": overlap[:10],
        "consider_learning": missing[:10],
        "skills_known_count": len(skills_known),
    }


def _total_jobs(session) -> int:
    return session.execute(text("SELECT COUNT(*) FROM jobsql")).scalar() or 0


def answer_question(client, session, question: str) -> dict:
    """
    Returns {"answer": str, "grounded": bool, "data_used": dict | None}
    """
    cls = _classify(client, question)
    cat = cls["category"]
    role = _normalize_role(cls["role"])

    if cat == "off_topic":
        return {"answer": _OFF_TOPIC_REPLY, "grounded": False, "data_used": None}

    n_jobs = _total_jobs(session)
    data: dict = {}

    try:
        if cat == "skills_for_role" and role:
            data["top_skills_for_role"] = _fetch_skills_for_role(session, role)
            data["role_searched"] = role
        elif cat == "top_skills":
            data["top_skills"] = _fetch_top_skills(session)
        elif cat == "top_companies":
            data["top_companies"] = _fetch_top_companies(session, role=role or None)
            if role:
                data["role_searched"] = role
        elif cat == "role_overview" and role:
            data["role_overview"] = _fetch_role_overview(session, role)
            data["role_searched"] = role
        elif cat == "skill_gap" and role:
            data["skill_gap"] = _fetch_skill_gap(session, role, cls["skills_known"])
            data["role_searched"] = role
        else:
            return {"answer": _OFF_TOPIC_REPLY, "grounded": False, "data_used": None}

        if not any(v for v in data.values() if v):
            return {
                "answer": (
                    f"I couldn't find enough data on '{role}' in our current postings. "
                    "Try a more common role title (e.g. 'data engineer', 'ml engineer')."
                ),
                "grounded": False,
                "data_used": data,
            }

        answer = _llm_call(
            client,
            _ANSWER_PROMPT.format(
                question=question,
                n_jobs=n_jobs,
                data=json.dumps(data, indent=2),
            ),
        ).strip()
        return {"answer": answer, "grounded": True, "data_used": data}

    except Exception as e:
        logger.error(f"Q&A failed: {e}")
        return {
            "answer": "Something went wrong looking that up. Try rephrasing the question.",
            "grounded": False,
            "data_used": None,
        }
