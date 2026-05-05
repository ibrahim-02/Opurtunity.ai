from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File

from api.schemas import SearchResponse, JobResult
from api.deps import get_client, get_session, limiter
from rag.resume_parser import parse_resume_text, extract_resume_text
from rag.search import (
    SearchFilters,
    embed_query,
    vector_search,
    hybrid_score,
    explain_jobs,
)

router = APIRouter()

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_MATCH_TOP_N = 15
_MATCH_CANDIDATES = 50
_ALLOWED_EXTS = (".pdf", ".docx")


@router.post("/match-resume", response_model=SearchResponse)
@limiter.limit("10/minute;50/day")
async def match_resume(
    request: Request,
    client=Depends(get_client),
    session=Depends(get_session),
    file: UploadFile = File(...),
):
    """
    Upload a PDF or DOCX resume → returns the top 15 matching jobs with explanations.
    No filters applied. Resume-mode skill scoring uses 35% threshold of the job's skills.
    """
    name = file.filename.lower()
    if not name.endswith(_ALLOWED_EXTS):
        raise HTTPException(status_code=422, detail="Only .pdf or .docx files are supported")

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    try:
        resume_text = extract_resume_text(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read resume: {e}")
    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="Resume contains no extractable text")

    parsed = parse_resume_text(resume_text, client)
    resume_skills = parsed.get("skills", [])
    summary = parsed.get("summary") or resume_text[:500]

    # Embed the summary (focused on profile) — better signal than raw resume text
    query_vec = embed_query(client, summary[:4000])

    # No extra filters — return raw top candidates
    raw = vector_search(session, query_vec, k=_MATCH_CANDIDATES, filters=SearchFilters())

    scored = hybrid_score(
        raw,
        summary,
        resume_skills=resume_skills or None,
    )
    final = scored[:_MATCH_TOP_N]

    explanations = explain_jobs(client, summary, final)

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
        query_used=summary[:200],
    )
