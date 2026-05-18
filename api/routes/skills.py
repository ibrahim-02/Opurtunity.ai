from fastapi import APIRouter, Depends

from api.schemas import PopularSkillsResponse
from api.deps import get_session
from sqlalchemy import text

router = APIRouter()


@router.get("/skills/popular", response_model=PopularSkillsResponse)
async def popular_skills(session=Depends(get_session), limit: int = 100):
    """Return the most commonly listed skills across all jobs — used for filter dropdown."""
    rows = session.execute(text("""
        SELECT skill, COUNT(*) AS cnt
        FROM jobsql,
             jsonb_array_elements_text(skills_extracted->'required_skills') AS skill
        WHERE skills_extracted IS NOT NULL
        GROUP BY skill
        ORDER BY cnt DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    return PopularSkillsResponse(skills=[r.skill for r in rows])
