from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

from api.schemas import ParseResumeResponse
from api.deps import get_client, limiter
from rag.resume_parser import parse_resume_text, parse_resume_pdf

router = APIRouter()

_MAX_TEXT_LEN = 20_000
_MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/parse-resume", response_model=ParseResumeResponse)
@limiter.limit("5/minute;20/day")
async def parse_resume(
    request: Request,
    client=Depends(get_client),
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
):
    if file:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=422, detail="Only PDF files are supported")
        content = await file.read()
        if len(content) > _MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="PDF too large (max 5 MB)")
        result = parse_resume_pdf(content, client)
    elif text:
        if len(text) > _MAX_TEXT_LEN:
            text = text[:_MAX_TEXT_LEN]
        result = parse_resume_text(text, client)
    else:
        raise HTTPException(status_code=422, detail="Provide a PDF file or resume text")

    return ParseResumeResponse(**result)
