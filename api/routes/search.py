from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import SearchRequest, SearchResponse, JobResult
from api.deps import get_client, get_session, limiter
from rag.resume_parser import parse_resume_text
from rag.search import SearchFilters, embed_query, vector_search, hybrid_score

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
@limiter.limit("20/minute;100/day")
async def search_jobs(request: Request, body: SearchRequest,
                      client=Depends(get_client), session=Depends(get_session)):
    query_text = body.query or body.resume_text
    if not query_text or not query_text.strip():
        raise HTTPException(status_code=422, detail="Provide query or resume_text")

    f = body.filters

    # Parse resume skills for scoring if resume_text provided
    resume_skills: list[str] = []
    if body.resume_text and body.resume_text.strip():
        parsed = parse_resume_text(body.resume_text, client)
        resume_skills = parsed.get("skills", [])

    filters = SearchFilters(
        min_years=f.min_years,
        skills=f.skills,
        location=f.location,
        max_hours_old=f.max_hours_old,
    )

    query_vec = embed_query(client, query_text[:4000])
    raw = vector_search(session, query_vec, k=body.candidates, filters=filters)
    scored = hybrid_score(
        raw,
        query_text,
        filter_skills=f.skills or None,
        resume_skills=resume_skills or None,
        min_years=f.min_years,
    )
    final = scored[:body.top_n]

    results = [
        JobResult(
            id=j["id"],
            title=j["title"],
            company=j.get("company"),
            location=j.get("location"),
            experience_years=j.get("experience_years"),
            skills=j.get("skills", []),
            link=j["link"],
            source=j.get("source"),
            hours_since_posted=j.get("hours_since_posted"),
            vec_score=round(j["vec_score"], 4),
            hybrid_score=round(j.get("hybrid_score", j["vec_score"]), 4),
            skill_overlap=round(j.get("skill_overlap", 0.0), 4),
            filter_score=round(j.get("filter_score", 1.0), 4),
            exp_score=round(j.get("exp_score", 1.0), 4),
        )
        for j in final
    ]
    return SearchResponse(results=results, total=len(results), query_used=query_text[:200])
