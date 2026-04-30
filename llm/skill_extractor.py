import json
import re

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from llm.ollama_client import OllamaClient
from llm.prompts import SKILL_EXTRACTION_PROMPT


# ── Hard blocklist (lowercase, exact match after normalisation) ───────────────
_BLOCKLIST = {
    # generic field/category labels
    "ai", "ml", "ai/ml", "ml/ai",
    "engineering", "software engineering", "software", "development", "developer",
    "computer science", "computer engineering",
    "mathematics", "math", "statistics",
    "programming", "coding",
    "technology", "information technology", "it",
    "data", "data science", "data analytics", "analytics",
    "machine learning", "deep learning", "artificial intelligence",
    "cloud", "cloud computing", "devops", "mlops", "dataops",
    "research",
    # soft skills / phrases
    "communication", "leadership", "teamwork", "problem solving", "problem-solving",
    "collaboration", "stakeholder management",
    "data-driven", "fast-paced", "cross-functional", "agile mindset",
    # degrees
    "bachelor", "bachelors", "bachelor's", "master", "masters", "master's",
    "phd", "ph.d", "ph.d.", "doctorate",
    # filler words
    "experience", "skills", "tools", "frameworks", "platforms", "languages",
    "english", "fluent",
}

# Tokens shorter than this (after stripping) are dropped — catches "glo", "AI"
_MIN_LEN = 3

# Some allow-listed short tokens that must not be dropped by length rule
_SHORT_ALLOWED = {"go", "r", "c", "c#", "c++", "f#", "vb", "qa", "ui", "ux", "qa/qe"}

_NORMALIZE = {
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mssql": "SQL Server",
    "ms sql": "SQL Server",
    "microsoft sql server": "SQL Server",
    "amazon web services": "AWS",
    "google cloud platform": "GCP",
    "google cloud": "GCP",
    "microsoft azure": "Azure",
    "microsoft power bi": "Power BI",
    "powerbi": "Power BI",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _filter_skills(
    raw_skills: list[str],
    description: str,
    company_name: str | None,
) -> list[str]:
    """
    Post-process LLM output:
    1. Drop blocklisted generic terms / soft skills / degrees
    2. Drop the company name (and obvious team-name fragments)
    3. Drop tokens < _MIN_LEN unless allow-listed
    4. Cross-check: skill must appear in the source description (case-insensitive)
       — kills hallucinations the LLM emits that aren't actually in the JD
    5. Normalize canonical forms (Postgres → PostgreSQL, etc.)
    6. Dedupe (case-insensitive)
    """
    desc_lower = description.lower() if description else ""
    company_lower = _norm(company_name) if company_name else None

    # also block first word of multi-word company names (e.g. "Roblox Corp" → block "roblox")
    company_tokens: set[str] = set()
    if company_lower:
        company_tokens.add(company_lower)
        for tok in re.split(r"[\s,.&]+", company_lower):
            tok = tok.strip().lower()
            if tok and tok not in {"inc", "corp", "llc", "ltd", "co", "the"}:
                company_tokens.add(tok)

    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_skills:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue

        norm = _norm(s)

        # length floor
        if len(norm) < _MIN_LEN and norm not in _SHORT_ALLOWED:
            continue

        # blocklist
        if norm in _BLOCKLIST:
            continue

        # company-name match
        if norm in company_tokens:
            continue

        # cross-check: skill must appear in source text (substring, case-insensitive)
        if desc_lower and norm not in desc_lower:
            continue

        # canonical form
        canonical = _NORMALIZE.get(norm, s)

        # dedupe (case-insensitive)
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)

    return out


class SkillExtractor:
    def __init__(self, client: OllamaClient):
        self.client = client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _call_llm(self, prompt: str) -> str:
        return self.client.generate(prompt)

    def extract(
        self,
        description: str,
        company_name: str | None = None,
    ) -> list[str] | None:
        """
        Returns list of cleaned skills, or None on hard failure.
        Empty list [] is a valid result (no skills mentioned).
        """
        truncated = description[:4000]
        prompt = SKILL_EXTRACTION_PROMPT.format(description=truncated)
        try:
            raw = self._call_llm(prompt)
            parsed = json.loads(raw)
            skills = parsed.get("skills", [])
            if not isinstance(skills, list):
                return None
            return _filter_skills(skills, description, company_name)
        except json.JSONDecodeError as e:
            logger.warning(f"Skill extraction JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Skill extraction failed: {e}")
            return None
