from collections import OrderedDict

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
    filter_staffing_linkedin,
    apply_source_diversity,
)

router = APIRouter()

# Cache: raw query text → (clean_query, extracted_filters, query_vector)
# Keyed on the raw query so filter-only changes skip the LLM + embedding round-trip.
_CACHE_MAX = 50
_query_cache: OrderedDict[str, tuple[str, dict, list[float]]] = OrderedDict()


def _cache_get(key: str) -> tuple[str, dict, list[float]] | None:
    k = key[:500]
    if k in _query_cache:
        _query_cache.move_to_end(k)
        return _query_cache[k]
    return None


def _cache_set(key: str, value: tuple[str, dict, list[float]]) -> None:
    k = key[:500]
    if k in _query_cache:
        _query_cache.move_to_end(k)
    else:
        if len(_query_cache) >= _CACHE_MAX:
            _query_cache.popitem(last=False)
    _query_cache[k] = value


@router.post("/search", response_model=SearchResponse)
@limiter.limit("20/minute;100/day")
async def search_jobs(request: Request, body: SearchRequest,
                      client=Depends(get_client), session=Depends(get_session)):
    query_text = body.query or body.resume_text
    if not query_text or not query_text.strip():
        raise HTTPException(status_code=422, detail="Provide query or resume_text")

    f = body.filters

    # Reuse intent + embedding when the query text hasn't changed (filters-only update).
    cached = _cache_get(query_text)
    if cached:
        clean_query, extracted, query_vec = cached
    else:
        clean_query, extracted = parse_query_intent(client, query_text)
        query_vec = embed_query(client, clean_query[:4000])
        _cache_set(query_text, (clean_query, extracted, query_vec))

    # Explicitly provided filters always win over LLM-extracted ones.
    # Location excluded from LLM extraction — it hallucinates "United States" for generic queries.
    merged_location  = f.location or None
    merged_min_years = f.min_years   if f.min_years   is not None else extracted.get("min_years")
    merged_skills    = f.skills      or extracted.get("skills", [])
    merged_max_hours = f.max_hours_old if f.max_hours_old is not None else extracted.get("max_hours_old")

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
        sources=f.sources or [],
        title_aliases=extracted.get("title_aliases", []),
    )

    raw = vector_search(session, query_vec, k=body.candidates, filters=filters, query_text=clean_query)
    scored = hybrid_score(
        raw,
        clean_query,
        filter_skills=merged_skills or None,
        resume_skills=resume_skills or None,
        min_years=merged_min_years,
    )
    scored = filter_staffing_linkedin(scored)
    # Build a pool of up to 5 pages, then slice the requested page.
    pool = apply_source_diversity(scored, body.top_n * 5)
    pool.sort(key=lambda x: x["vec_score"], reverse=True)
    total = len(pool)
    start = (body.page - 1) * body.top_n
    final = pool[start: start + body.top_n]

    # Explanations are fetched asynchronously by the frontend batch effect —
    # no blocking LLM call here so search response returns immediately.
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
            explanation=None,
        )
        for j in final
    ]
    return SearchResponse(
        results=results,
        total=total,
        query_used=clean_query[:200],
        filters_used=FiltersUsed(
            location=merged_location,
            min_years=merged_min_years,
            skills=merged_skills,
            max_hours_old=merged_max_hours,
        ),
    )
