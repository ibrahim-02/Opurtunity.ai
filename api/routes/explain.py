from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import ExplainRequest, ExplainResponse
from api.deps import get_client, get_session, limiter
from models.db_models import JobSQL
from rag.search import explain_jobs

router = APIRouter()


@router.post("/explain", response_model=ExplainResponse)
@limiter.limit("30/minute;200/day")
async def explain(
    request: Request,
    body: ExplainRequest,
    client=Depends(get_client),
    session=Depends(get_session),
):
    """
    Generate one-sentence "why this matches" for a list of jobs given a query.
    Used by the frontend to fill in explanations after results land.
    """
    rows = (
        session.query(JobSQL)
        .filter(JobSQL.id.in_(body.job_ids))
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No jobs found for given ids")

    def _flatten_skills(s) -> list:
        if isinstance(s, list):
            return s
        if isinstance(s, dict):
            return s.get("required_skills", []) or []
        return []

    jobs = [
        {
            "id": r.id,
            "title": r.title,
            "company": r.company_name,
            "location": r.location,
            "experience_years": r.experience_years,
            "skills": _flatten_skills(r.skills_extracted),
        }
        for r in rows
    ]

    explanations = explain_jobs(client, body.query, jobs)
    return ExplainResponse(explanations=explanations)
