from fastapi import APIRouter, Depends, Request

from api.schemas import AskRequest, AskResponse
from api.deps import get_client, get_session, limiter
from rag.career_qa import answer_question

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
@limiter.limit("20/minute;100/day")
async def ask(
    request: Request,
    body: AskRequest,
    client=Depends(get_client),
    session=Depends(get_session),
):
    result = answer_question(client, session, body.question)
    return AskResponse(
        answer=result["answer"],
        grounded=result["grounded"],
        data_used=result.get("data_used"),
    )
