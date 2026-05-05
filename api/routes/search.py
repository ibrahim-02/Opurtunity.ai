from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import SearchRequest, SearchResponse, JobResult, FiltersUsed
from api.deps import get_client, get_session, limiter
from rag.resume_parser import parse_resume_text
from rag.search import (
    SearchFilters,
    embed_query,
    vector_search,
    hybrid_score,
    parse_query_intent,
    explain_jobs,
)

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
@limiter.limit("20/minute;100/day")
async def search_jobs(request: Request, body: SearchRequest,
                      client=Depends(get_client), session=Depends(get_session)):
    query_text = body.query or body.resume_text
    if not query_text or not query_text.strip():
        raise HTTPException(status_code=422, detail="Provide query or resume_text")

    f = body.filters

    # LLM extracts clean query + filters from natural language.
    # Explicitly provided filters always win over extracted ones.
    clean_query, extracted = parse_query_intent(client, query_text)
    merged_location    = f.location    or extracted.get("location")
    merged_min_years   = f.min_years   if f.min_years   is not None else extracted.get("min_years")
    merged_skills      = f.skills      or extracted.get("skills", [])
    merged_max_hours   = f.max_hours_old if f.max_hours_old is not None else extracted.get("max_hours_old")

    # Parse resume skills for scoring if resume_text provided
    resume_skills: list[str] = []
    if body.resume_text and body.resume_text.strip():
        parsed = parse_resume_text(body.resume_text, client)
        resume_skills = parsed.get("skills", [])

    filters = SearchFilters(
        min_years=merged_min_years,
        skills=merged_skills,
        location=merged_location,
        max_hours_old=merged_max_hours,
    )

    query_vec = embed_query(client, clean_query[:4000])
    raw = vector_search(session, query_vec, k=body.candidates, filters=filters)
    scored = hybrid_score(
        raw,
        clean_query,
        filter_skills=merged_skills or None,
        resume_skills=resume_skills or None,
        min_years=merged_min_years,
    )
    final = scored[:body.top_n]

    # Single LLM call returns one-sentence "why it matches" per result
    explanations = explain_jobs(client, clean_query, final)

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
            explanation=explanations.get(j["id"]),
        )
        for j in final
    ]
    return SearchResponse(
        results=results,
        total=len(results),
        query_used=clean_query[:200],
        filters_used=FiltersUsed(
            location=merged_location,
            min_years=merged_min_years,
            skills=merged_skills,
            max_hours_old=merged_max_hours,
        ),
    )
