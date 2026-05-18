from pydantic import BaseModel, Field


class SearchFiltersSchema(BaseModel):
    min_years: int | None = Field(None, ge=0, le=30)
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    max_hours_old: int | None = Field(720, ge=1)  # default: last 30 days
    sources: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str | None = None
    resume_text: str | None = None
    filters: SearchFiltersSchema = Field(default_factory=SearchFiltersSchema)
    top_n: int = Field(20, ge=1, le=100)
    candidates: int = Field(250, ge=10, le=500)
    page: int = Field(1, ge=1, le=10)


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
    explanation: str | None = None


class FiltersUsed(BaseModel):
    location: str | None = None
    min_years: int | None = None
    skills: list[str] = Field(default_factory=list)
    max_hours_old: int | None = None


class SearchResponse(BaseModel):
    results: list[JobResult]
    total: int
    query_used: str
    filters_used: FiltersUsed | None = None


class PopularSkillsResponse(BaseModel):
    skills: list[str]


class ExplainRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    job_ids: list[int] = Field(min_length=1, max_length=30)


class ExplainResponse(BaseModel):
    explanations: dict[int, str]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    data_used: dict | None = None
