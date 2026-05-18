"""
Hybrid RAG job search with filters.

Retrieval strategy:
  1. Embed query/resume with RETRIEVAL_QUERY task type (Vertex AI)
  2. Vector search: top-K by cosine similarity (pgvector) — filters applied here
  3. Hybrid re-score: vector_score * 0.7 + skill_overlap * 0.3
  4. LLM rerank: Gemini picks best N from the top-K candidates (optional)

Usage:
    python -m rag.search "Python backend engineer with Kubernetes experience"
    python -m rag.search "data scientist pytorch sql" --top 5 --candidates 20
    python -m rag.search --resume path/to/resume.txt --location "New York" --max-years 5
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal
from llm.factory import get_llm_client

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")


# ── Filters ───────────────────────────────────────────────────────────────────

@dataclass
class SearchFilters:
    min_years: int | None = None
    skills: list[str] = field(default_factory=list)
    location: str | None = None
    match_mode: str = "manual"   # "manual" = all must match | "resume" = 50% threshold
    max_hours_old: int | None = None
    sources: list[str] = field(default_factory=list)  # empty = all sources
    title_aliases: list[str] = field(default_factory=list)  # alternative titles for the same role


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_query(client, query: str) -> list[float]:
    """
    Embed a search query using the client's query-optimised method.
    Vertex: uses RETRIEVAL_QUERY task type for asymmetric retrieval.
    Ollama: falls back to the same embed() call (no task-type concept).
    """
    return client.embed_query(query)


# ── Vector search with filters ────────────────────────────────────────────────

def _vec_str(v: list[float]) -> str:
    return "[" + ",".join(str(x) for x in v) + "]"


def vector_search(
    session,
    query_vec: list[float],
    k: int = 20,
    filters: SearchFilters | None = None,
    query_text: str | None = None,
) -> list[dict]:
    f = filters or SearchFilters()

    from datetime import datetime, timezone, timedelta
    min_posted_date = (
        datetime.now(timezone.utc) - timedelta(hours=f.max_hours_old)
        if f.max_hours_old else None
    )

    params: dict = {
        "vec": _vec_str(query_vec),
        "k": k,
        "location_pattern": f"%{f.location}%" if f.location else None,
        "min_posted_date": min_posted_date,
        "query_text": query_text or None,
    }

    source_clause = ""
    if f.sources:
        placeholders = ", ".join(f":src_{i}" for i in range(len(f.sources)))
        source_clause = f"AND source IN ({placeholders})"
        for i, s in enumerate(f.sources):
            params[f"src_{i}"] = s

    rows = session.execute(text(f"""
        SELECT
            id,
            title,
            company_name,
            location,
            experience_years,
            skills_extracted,
            link,
            source,
            1 - (embedding <=> CAST(:vec AS vector)) AS vec_score,
            CASE
                WHEN posted_date IS NOT NULL
                THEN EXTRACT(EPOCH FROM (NOW() - posted_date))::INTEGER / 3600
                ELSE NULL
            END AS hours_since_posted,
            CASE
                WHEN :query_text IS NULL THEN 0.0
                ELSE COALESCE(ts_rank(
                    to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(company_name, '')),
                    plainto_tsquery('english', :query_text)
                ), 0.0)
            END AS title_bm25
        FROM jobsql
        WHERE embedding IS NOT NULL
          AND (:location_pattern IS NULL
               OR location ILIKE :location_pattern)
          AND (:min_posted_date IS NULL
               OR posted_date >= :min_posted_date)
          {source_clause}
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :k
    """), params).fetchall()

    def _row_to_dict(r) -> dict:
        skills = []
        if r.skills_extracted:
            s = r.skills_extracted
            if isinstance(s, str):
                s = json.loads(s)
            skills = s.get("required_skills", []) if isinstance(s, dict) else []
        return {
            "id": r.id,
            "title": r.title,
            "company": r.company_name,
            "location": r.location,
            "experience_years": r.experience_years,
            "skills": skills,
            "link": r.link,
            "source": r.source,
            "hours_since_posted": int(r.hours_since_posted) if r.hours_since_posted is not None else None,
            "vec_score": float(r.vec_score),
            "title_bm25": float(r.title_bm25) if r.title_bm25 is not None else 0.0,
        }

    results = [_row_to_dict(r) for r in rows]
    seen_ids = {r["id"] for r in results}

    # Fetch jobs matching alternative titles and merge (deduped) into candidates
    if f.title_aliases:
        alias_clauses = " OR ".join(f"title ILIKE :alias_{i}" for i in range(len(f.title_aliases)))
        alias_params = {**params}
        for i, alias in enumerate(f.title_aliases):
            alias_params[f"alias_{i}"] = f"%{alias}%"

        alias_rows = session.execute(text(f"""
            SELECT
                id, title, company_name, location, experience_years,
                skills_extracted, link, source,
                1 - (embedding <=> CAST(:vec AS vector)) AS vec_score,
                CASE
                    WHEN posted_date IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (NOW() - posted_date))::INTEGER / 3600
                    ELSE NULL
                END AS hours_since_posted,
                CASE
                    WHEN :query_text IS NULL THEN 0.0
                    ELSE COALESCE(ts_rank(
                        to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(company_name, '')),
                        plainto_tsquery('english', :query_text)
                    ), 0.0)
                END AS title_bm25
            FROM jobsql
            WHERE embedding IS NOT NULL
              AND ({alias_clauses})
              AND (:location_pattern IS NULL OR location ILIKE :location_pattern)
              AND (:min_posted_date IS NULL OR posted_date >= :min_posted_date)
              {source_clause}
            LIMIT 50
        """), alias_params).fetchall()

        for r in alias_rows:
            if r.id not in seen_ids:
                results.append(_row_to_dict(r))
                seen_ids.add(r.id)

    return results


# ── Hybrid re-scoring ─────────────────────────────────────────────────────────

import math as _math

def _extract_query_skills(query: str) -> set[str]:
    stopwords = {
        "engineer", "engineering", "senior", "junior", "lead", "staff",
        "developer", "manager", "analyst", "scientist", "experience",
        "years", "with", "and", "or", "for", "the", "in", "on", "at",
        "using", "knowledge", "strong", "good", "background",
    }
    tokens = set(re.findall(r"[a-z][a-z0-9+#./]*", query.lower()))
    return tokens - stopwords


def _filter_skill_score(
    job_skills: list[str],
    filter_skills: list[str],
    mode: str,
) -> float:
    """
    Score how well a job's skills satisfy the filter.

    manual mode: score = matched / total_filter_skills
      - All 2 filter skills present → 1.0
      - Only 1 of 2 → 0.5
      - None → 0.0

    resume mode: threshold = ceil(35% of the JOB's required skills), min 1
      - Resumes typically list 30-40 skills, jobs list 5-15.
      - If 35% of the job's skills are covered by the resume → score 1.0.
      - Job needs [Python, AWS, Docker] (3), resume covers 1 → matched/1 = 1.0
      - Job needs 10 skills, resume covers 2 → matched/4 = 0.5
    """
    if not filter_skills:
        return 1.0
    job_lower = {s.lower() for s in job_skills}
    matched = sum(1 for s in filter_skills if s.lower() in job_lower)

    if mode == "manual":
        return matched / len(filter_skills)
    else:  # resume
        if not job_skills:
            return 0.0
        threshold = max(1, _math.ceil(len(job_skills) * 0.35))
        return min(matched / threshold, 1.0)


def _recency_score(hours_since_posted: int | None) -> float:
    """
    Exponential decay with a 14-day half-life.
      0h  → 1.0   (just posted)
      24h → 0.95
      7d  → 0.70
      14d → 0.50
      30d → 0.22
    Jobs with no posted_date get a neutral 0.40 so they sink below fresh listings.
    """
    if hours_since_posted is None:
        return 0.40
    return _math.exp(-_math.log(2) * hours_since_posted / 336)


def _experience_score(job_years: int | None, min_years: int | None) -> float:
    """
    Score how well a job's experience requirement matches the user's filter.
    - job_years >= min_years  → 1.0  (exact or above — perfect)
    - job_years < min_years   → job_years / min_years  (partial penalty)
    - job_years is null       → 0.6  (not stated — neutral, slight penalty)
    - min_years is None       → 1.0  (no filter set — no penalty)
    """
    if min_years is None:
        return 1.0
    if job_years is None:
        return 0.6
    if job_years >= min_years:
        return 1.0
    return round(job_years / min_years, 4)


def hybrid_score(
    candidates: list[dict],
    query: str,
    filter_skills: list[str] | None = None,
    resume_skills: list[str] | None = None,
    min_years: int | None = None,
) -> list[dict]:
    """
    Weights per mode — recency is always the #2 signal to surface fresh postings.

    Pure semantic (no filters):
        vec=0.50  recency=0.25  title_bm25=0.15  overlap=0.10

    Manual skills filter:
        vec=0.30  filter=0.30  recency=0.20  title_bm25=0.10  overlap=0.10

    Resume skills:
        vec=0.30  filter=0.30  recency=0.20  title_bm25=0.10  overlap=0.10

    Manual + experience years:
        vec=0.25  filter=0.25  exp=0.20  recency=0.20  title_bm25=0.05  overlap=0.05
    """
    has_filter = bool(filter_skills)
    has_resume = bool(resume_skills)
    has_years  = min_years is not None
    query_tokens = _extract_query_skills(query)

    #                      vec    filter  exp     overlap  title   recency
    if has_filter and has_years:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.25, 0.25, 0.20, 0.05, 0.05, 0.20
    elif has_filter:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.30, 0.30, 0.00, 0.10, 0.10, 0.20
    elif has_resume and has_years:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.25, 0.25, 0.20, 0.05, 0.05, 0.20
    elif has_resume:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.30, 0.30, 0.00, 0.10, 0.10, 0.20
    elif has_years:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.35, 0.00, 0.30, 0.10, 0.10, 0.15
    else:
        w_vec, w_filter, w_exp, w_overlap, w_title, w_rec = 0.50, 0.00, 0.00, 0.10, 0.15, 0.25

    for c in candidates:
        job_skills = c["skills"]
        job_lower  = {s.lower() for s in job_skills}
        # Include title words so "machine learning" in query matches title "Machine Learning Eng"
        title_words = set(re.findall(r"[a-z][a-z0-9+#./]*", (c.get("title") or "").lower()))
        overlap_set = job_lower | title_words

        query_overlap  = (
            len(query_tokens & overlap_set) / max(len(query_tokens), 1)
            if query_tokens else 0.0
        )
        manual_score   = _filter_skill_score(job_skills, filter_skills, "manual") if has_filter else 1.0
        resume_score   = _filter_skill_score(job_skills, resume_skills, "resume") if has_resume else 1.0
        filter_score   = manual_score * resume_score
        exp_score      = _experience_score(c.get("experience_years"), min_years)
        title_bm25     = min(c.get("title_bm25", 0.0) * 2.0, 1.0)
        rec_score      = _recency_score(c.get("hours_since_posted"))

        c["skill_overlap"]  = round(query_overlap, 4)
        c["filter_score"]   = round(filter_score, 4)
        c["exp_score"]      = round(exp_score, 4)
        c["hybrid_score"]   = round(
            w_vec    * c["vec_score"]
            + w_filter * filter_score
            + w_exp    * exp_score
            + w_overlap * query_overlap
            + w_title  * title_bm25
            + w_rec    * rec_score,
            4,
        )

    return sorted(candidates, key=lambda x: x["hybrid_score"], reverse=True)


# ── LLM rerank ────────────────────────────────────────────────────────────────

_RERANK_PROMPT = """You are a job-matching assistant. Given a candidate query and a list of job postings, rank the jobs from most to least relevant.

Candidate query:
\"\"\"{query}\"\"\"

Jobs (JSON array):
{jobs_json}

Return ONLY a JSON array of job IDs in order of relevance (best match first).
Example: [42, 7, 15, 3, 28]
"""


def llm_rerank(client, query: str, candidates: list[dict], top_n: int) -> list[dict]:
    jobs_json = json.dumps([
        {
            "id": c["id"],
            "title": c["title"],
            "company": c["company"],
            "skills": c["skills"][:15],
            "experience_years": c["experience_years"],
        }
        for c in candidates
    ], indent=2)
    prompt = _RERANK_PROMPT.format(query=query, jobs_json=jobs_json)
    try:
        raw = client.generate(prompt)
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        ranked_ids = json.loads(raw)
        if not isinstance(ranked_ids, list):
            raise ValueError("Expected list")
        id_to_job = {c["id"]: c for c in candidates}
        reranked = [id_to_job[i] for i in ranked_ids if i in id_to_job]
        seen = {c["id"] for c in reranked}
        for c in candidates:
            if c["id"] not in seen:
                reranked.append(c)
        return reranked[:top_n]
    except Exception as e:
        logger.warning(f"LLM rerank failed ({e}), using hybrid score")
        return candidates[:top_n]


# ── Display ───────────────────────────────────────────────────────────────────

def display(results: list[dict]):
    print("\n" + "=" * 70)
    print(f"  TOP {len(results)} MATCHES")
    print("=" * 70)
    for i, job in enumerate(results, 1):
        yrs = f"{job['experience_years']}+ yrs" if job["experience_years"] else "not stated"
        skills_preview = ", ".join(job["skills"][:8])
        print(f"\n#{i}  {job['title']} @ {job['company']}")
        print(f"    Location : {job['location'] or 'N/A'}")
        print(f"    Exp      : {yrs}")
        print(f"    Skills   : {skills_preview or 'N/A'}")
        print(f"    Score    : vec={job['vec_score']:.3f}  hybrid={job.get('hybrid_score', job['vec_score']):.3f}")
        print(f"    Link     : {job['link']}")
    print("=" * 70 + "\n")


# ── LLM intent extraction ─────────────────────────────────────────────────────

_INTENT_PROMPT = """Extract structured job search parameters from the user's natural language query.

User query: "{query}"

Return a JSON object with exactly these fields:
{{
  "query": "job role + industry/domain/company-type context if mentioned (e.g. 'Data Scientist in Fintech', 'ML Engineer at a healthcare startup', 'Backend Engineer in e-commerce'). Include the domain so results stay relevant to that sector. Omit filler words like 'jobs', 'position', 'role'.",
  "location": "location if explicitly mentioned, fully normalized (US → United States, NYC → New York) or null. Do NOT infer location if not stated.",
  "min_years": "years of experience as integer if mentioned, or null",
  "skills": ["specific technical skills only, e.g. Python, AWS, TensorFlow"] or [],
  "max_hours_old": "hours as integer if a time window mentioned (24=today, 168=this week, 720=this month) or null",
  "title_aliases": ["3 to 6 alternative job titles that employers commonly use for the same role. Only for well-known roles (e.g. 'Data Engineer' → ['Analytics Engineer', 'ETL Developer', 'Data Pipeline Engineer', 'Big Data Engineer']. 'Software Engineer' → ['Software Developer', 'SWE', 'Backend Developer', 'Full Stack Developer']. 'Product Manager' → ['Product Owner', 'Program Manager', 'Technical Product Manager']. 'Data Scientist' → ['ML Engineer', 'Applied Scientist', 'Research Scientist', 'AI Engineer']. 'DevOps Engineer' → ['Platform Engineer', 'Site Reliability Engineer', 'SRE', 'Infrastructure Engineer', 'Cloud Engineer']). Return [] if the role is niche, unclear, or already specific enough."]
}}

Rules:
- query: keep domain/industry/sector context — it is critical for relevance. 'data science in fintech' → 'Data Scientist in Fintech'. 'software engineer at a bank' → 'Software Engineer in Banking'.
- location: only extract if the user explicitly named a place. Never infer or assume a country.
- min_years: extract from "3+ years", "senior" → 5, "junior" → 0, "entry level" → 0
- skills: specific technologies only, not soft skills
- max_hours_old: null if no time window mentioned — do NOT default to 24
- title_aliases: only for well-known standard roles — return [] for vague or domain-specific queries
"""


def parse_query_intent(client, raw_query: str) -> tuple[str, dict]:
    """
    Use Gemini to extract a clean job query + structured filters from natural language.
    Returns (clean_query, filters_dict).
    Falls back to (raw_query, {}) on any failure.
    """
    try:
        prompt = _INTENT_PROMPT.format(query=raw_query.replace('"', "'"))
        raw = client.generate(prompt)
        import json as _json
        import re as _re
        raw = _re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = _json.loads(raw)
        clean_query = parsed.get("query") or raw_query
        filters = {
            "location":      parsed.get("location"),
            "min_years":     parsed.get("min_years"),
            "skills":        parsed.get("skills") or [],
            "max_hours_old": parsed.get("max_hours_old"),
            "title_aliases": parsed.get("title_aliases") or [],
        }
        logger.info(
            "Intent extracted: query='{}' location={} min_years={} skills={} max_hours_old={} aliases={}",
            clean_query, filters["location"], filters["min_years"],
            filters["skills"], filters["max_hours_old"], filters["title_aliases"],
        )
        return clean_query, filters
    except Exception as e:
        logger.warning("Intent extraction failed ({}), using raw query.", e)
        return raw_query, {}


# ── Search-time staffing agency filter (LinkedIn only) ────────────────────────

_STAFFING_NAME_RE = re.compile(
    r"\b(staffing|staffers?|recruit(?:ing|ment|ers?)?|placement|"
    r"headhunt(?:ers?|ing)?|outsourc(?:ing|e)|manpower|hiring)\b"
    r"|\bhire\b",
    re.IGNORECASE,
)


def filter_staffing_linkedin(results: list[dict]) -> list[dict]:
    """
    Hard-remove LinkedIn jobs whose company name contains known staffing/recruiting
    signals. Direct employers never name themselves 'XYZ Staffing' or 'ABC Recruiting'.

    For ambiguous names (e.g. 'AgileGrid Solutions'), the scraper-level
    company_mentioned_in_description filter already blocks new entries at insert time.
    This covers obvious cases already in the DB.
    """
    out = []
    for job in results:
        if (job.get("source") or "").lower() != "linkedin":
            out.append(job)
            continue
        company = job.get("company") or ""
        if _STAFFING_NAME_RE.search(company):
            logger.debug(
                "  [search:staffing_filter] removed '{}' @ '{}' — staffing signal in company name",
                job.get("title"), company,
            )
            continue
        out.append(job)
    return out


# ── Source diversity cap ──────────────────────────────────────────────────────

def apply_source_diversity(results: list[dict], top_n: int) -> list[dict]:
    """
    Enforce source mix in top_n results (already sorted by hybrid_score desc).
    Caps: LinkedIn ≤ 30%, Greenhouse ≤ 60%, Indeed ≤ 10%.
    Overflow slots filled by best remaining jobs from any source.
    """
    caps = {
        "linkedin":   max(1, round(top_n * 0.50)),
        "greenhouse": max(1, round(top_n * 0.30)),
        "indeed":     max(1, round(top_n * 0.20)),
    }
    counts: dict[str, int] = {}
    selected: list[dict] = []
    overflow: list[dict] = []

    for job in results:
        src = (job.get("source") or "other").lower()
        cap = caps.get(src, top_n)
        cnt = counts.get(src, 0)
        if cnt < cap:
            selected.append(job)
            counts[src] = cnt + 1
        else:
            overflow.append(job)
        if len(selected) >= top_n:
            break

    if len(selected) < top_n:
        selected.extend(overflow[: top_n - len(selected)])

    return selected


# ── Per-result explanation ────────────────────────────────────────────────────

_EXPLAIN_PROMPT = """A job seeker is searching for: "{query}"

Below are the top matching jobs. For each one, write a single short sentence (max 25 words) explaining why it matches the seeker's query. Mention specific skills, role, location, or experience that align — be concrete, not generic.

Jobs:
{jobs_json}

Return ONLY a JSON object mapping job id (as string) to its explanation:
{{
  "12": "5+ years Python and AWS — direct fit for senior ML role in NYC.",
  "47": "..."
}}
"""


def explain_jobs(client, query: str, jobs: list[dict]) -> dict[int, str]:
    """
    Single Gemini call that returns a one-sentence "why it matches" per job.
    Returns {job_id: explanation}. Falls back to {} on failure.
    """
    if not jobs:
        return {}
    try:
        compact = [
            {
                "id": j["id"],
                "title": j["title"],
                "company": j.get("company"),
                "location": j.get("location"),
                "experience_years": j.get("experience_years"),
                "skills": j.get("skills", [])[:12],
            }
            for j in jobs
        ]
        prompt = _EXPLAIN_PROMPT.format(
            query=query.replace('"', "'"),
            jobs_json=json.dumps(compact, indent=2),
        )
        raw = client.generate(prompt)
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(raw)
        return {int(k): str(v) for k, v in parsed.items() if v}
    except Exception as e:
        logger.warning("Explanation pass failed ({}), returning no explanations.", e)
        return {}


# ── Public search function (used by API) ──────────────────────────────────────

def search(
    query: str,
    filters: SearchFilters | None = None,
    top_n: int = 10,
    candidates: int = 30,
    rerank: bool = False,
    client=None,
    session=None,
) -> list[dict]:
    """
    Core search function. Returns a list of job dicts.
    Caller is responsible for closing session and client.
    If client/session are not provided, they are created and closed internally.
    """
    _own_session = session is None
    _own_client = client is None
    if _own_session:
        session = SessionLocal()
    if _own_client:
        client = get_llm_client()

    try:
        query_vec = embed_query(client, query)
        raw = vector_search(session, query_vec, k=candidates, filters=filters, query_text=query)
        scored = hybrid_score(raw, query)
        if rerank and len(scored) > top_n:
            return llm_rerank(client, query, scored, top_n)
        return scored[:top_n]
    finally:
        if _own_session:
            session.close()
        if _own_client:
            client.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid RAG job search")
    parser.add_argument("query", nargs="?", default=None, help="Free-text job query")
    parser.add_argument("--resume", type=str, default=None, help="Path to plain-text resume file")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--candidates", type=int, default=20)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--min-years", type=int, default=None)
    parser.add_argument("--skills", type=str, default=None, help="Comma-separated skills e.g. 'Python,AWS'")
    parser.add_argument("--location", type=str, default=None)
    args = parser.parse_args()

    if args.resume:
        query_text = Path(args.resume).read_text(encoding="utf-8")
    elif args.query:
        query_text = args.query
    else:
        parser.error("Provide a query string or --resume path")

    filters = SearchFilters(
        min_years=args.min_years,
        skills=[s.strip() for s in args.skills.split(",")] if args.skills else [],
        location=args.location,
    )

    results = search(
        query=query_text,
        filters=filters,
        top_n=args.top,
        candidates=args.candidates,
        rerank=not args.no_rerank,
    )
    display(results)
