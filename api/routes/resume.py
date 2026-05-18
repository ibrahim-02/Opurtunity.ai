from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from api.schemas import SearchResponse, JobResult
from api.deps import get_client, get_session, limiter
from rag.resume_parser import extract_resume_text, parse_resume_text
from rag.search import (
    SearchFilters,
    embed_query,
    vector_search,
    hybrid_score,
)

router = APIRouter()

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_MATCH_TOP_N = 20
_MATCH_CANDIDATES = 250
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

    query_vec = embed_query(client, summary[:4000])
    raw = vector_search(
        session, query_vec, k=_MATCH_CANDIDATES,
        filters=SearchFilters(max_hours_old=720),  # last 30 days
        query_text=summary[:500],
    )
    scored = hybrid_score(raw, summary, resume_skills=resume_skills or None)
    final = scored[:_MATCH_TOP_N]

    # Skip explanations here — frontend calls /api/explain after results land
    # so the user sees jobs in ~12s instead of waiting ~30s for the LLM pass.
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
        total=len(results),
        query_used=summary[:1000],
    )


@router.post("/tailor-with-research")
@limiter.limit("5/minute;20/day")
async def tailor_with_research(request: Request, job_id: int = None, client=Depends(get_client), session=Depends(get_session)):
    """
    Tailor resume for a specific job with company research context.
    Returns ATS-optimized PDF resume as binary.
    """
    if not job_id:
        raise HTTPException(status_code=422, detail="job_id is required")

    from sqlalchemy import text as sql_text
    from llm.company_researcher import CompanyResearcher
    from llm.resume_tailor import ResumeTailor
    from llm.resume_selector import load_base_resume, role_for_title
    from llm.section_parser import _strip_html
    from storage.gcs_client import GCSClient
    from storage.pdf_generator import render_resume_pdf

    # Fetch job
    job = session.execute(
        sql_text("SELECT id, title, company_name, description FROM jobsql WHERE id = :id"),
        {"id": job_id},
    ).fetchone()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_id, title, company, description = job

    # Load role-specific base resume from disk
    base_resume = load_base_resume(title or "")
    if not base_resume:
        raise HTTPException(status_code=500, detail="No base resume found for this role")

    # Get description text (may be stored in GCS)
    if description and description.startswith("gs://"):
        try:
            gcs = GCSClient()
            path = description.replace(f"gs://{gcs._bucket.name}/", "")
            text_content = gcs._bucket.blob(path).download_as_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not download description: {e}")
    else:
        text_content = description

    if not text_content or not text_content.strip():
        raise HTTPException(status_code=422, detail="Job has no description")

    text_content = _strip_html(text_content)

    try:
        # Research company
        researcher = CompanyResearcher(client)
        company_profile = researcher.research(text_content, company_name=company)
        if not company_profile:
            raise HTTPException(status_code=500, detail="Company research failed")

        # Tailor with research
        tailor = ResumeTailor(client)
        tailored = tailor.tailor_with_research(
            base_resume,
            text_content,
            title or "",
            company or "",
            company_profile,
        )
        if not tailored:
            raise HTTPException(status_code=500, detail="Resume tailoring failed")

        # Render PDF
        pdf_bytes = render_resume_pdf(tailored)

        from io import BytesIO
        return FileResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            filename=f"resume_{company.replace(' ', '_')}_{job_id}.pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tailoring failed: {e}")
