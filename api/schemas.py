from pydantic import BaseModel, Field


class SearchFiltersSchema(BaseModel):
    min_years: int | None = Field(None, ge=0, le=30)
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    max_hours_old: int | None = Field(None, ge=1)


class SearchRequest(BaseModel):
    query: str | None = None
    resume_text: str | None = None
    filters: SearchFiltersSchema = Field(default_factory=SearchFiltersSchema)
    top_n: int = Field(10, ge=1, le=500)
    candidates: int = Field(30, ge=10, le=500)


class JobResult(BaseModel):
    id: int
    title: str
    company: str | None
    location: str | None
    experience_years: int | None
    skills: list[str]
    link: str
    source: str | None
    hours_since_posted: int | None
    vec_score: float
    hybrid_score: float
    skill_overlap: float
    filter_score: float
    exp_score: float


class SearchResponse(BaseModel):
    results: list[JobResult]
    total: int
    query_used: str


class ParseResumeResponse(BaseModel):
    skills: list[str]
    experience_years: int | None
    summary: str


class PopularSkillsResponse(BaseModel):
    skills: list[str]
