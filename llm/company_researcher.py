"""
Analyze company values, culture, and tech stack from job description and optional website content.
Uses Gemini to extract structured company profile for resume tailoring context.
"""
import json
import re
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

_RESEARCH_PROMPT = """Analyze the provided company information and extract their values, culture, and tech stack.
Focus on what they actually care about based on the language, emphasis, and technologies mentioned.

Return ONLY a JSON object with these exact fields:
{{
  "company_name": "extracted or inferred from content",
  "core_values": ["value1", "value2", "value3"],
  "culture_keywords": ["keyword1", "keyword2"],
  "tech_stack": ["tech1", "tech2", "..."],
  "hiring_emphasis": "What this company emphasizes in hiring (2-3 sentences)",
  "ideal_candidate_profile": "Type of person they're looking for (1-2 sentences)"
}}

JOB DESCRIPTION:
{job_description}

{website_content_section}

Extract insights from the text. Be specific and grounded in what's actually stated.
"""


def _extract_company_name(text: str) -> str | None:
    """Try to extract company name from job description."""
    patterns = [
        r"^([A-Z][A-Za-z0-9\s]+)\s+(?:is |are |'s )",
        r"(?:at|for)\s+([A-Z][A-Za-z0-9\s&]+)(?:\s|,|$)",
        r"(?:company|organization)\s+(?:is\s+)?(?:called\s+)?([A-Z][A-Za-z0-9\s&]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:500])
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 50:
                return name
    return None


class CompanyResearcher:
    def __init__(self, client):
        self.client = client

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=5))
    def _call_llm(self, prompt: str) -> str:
        return self.client.generate(prompt)

    def _parse_research(self, raw: str) -> dict | None:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or "company_name" not in data:
                logger.warning("Research output missing required fields")
                return None
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Research LLM returned invalid JSON: {e}")
            return None

    def research(
        self,
        job_description: str,
        company_name: str | None = None,
        website_content: str | None = None,
    ) -> dict | None:
        """
        Analyze company from job description and optional website content.
        Returns structured company profile or None on failure.
        """
        if not job_description or not job_description.strip():
            logger.warning("Empty job description")
            return None

        website_section = ""
        if website_content:
            website_section = f"""
COMPANY WEBSITE CONTENT (careers/about page):
{website_content[:2000]}
"""

        prompt = _RESEARCH_PROMPT.format(
            job_description=job_description[:4000],
            website_content_section=website_section,
        )

        try:
            raw = self._call_llm(prompt)
        except Exception as e:
            logger.error(f"Company research failed: {e}")
            return None

        profile = self._parse_research(raw)
        if not profile:
            return None

        if company_name and not profile.get("company_name"):
            profile["company_name"] = company_name

        logger.info(f"Researched company: {profile.get('company_name', 'unknown')}")
        return profile
