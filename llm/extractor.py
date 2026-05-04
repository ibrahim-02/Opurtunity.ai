import json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from llm.ollama_client import OllamaClient
from llm.prompts import EXTRACTION_PROMPT
from models.pydantic_models import JobExtracted


class JobExtractor:
    def __init__(self, client: OllamaClient):
        self.client = client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _call_llm(self, prompt: str) -> str:
        return self.client.generate(prompt)

    def extract(self, html: str, link: str) -> JobExtracted | None:
        truncated_html = html[:3000]
        prompt = EXTRACTION_PROMPT.format(html=truncated_html, link=link)
        try:
            raw_response = self._call_llm(prompt)
            parsed = json.loads(raw_response)
            if not parsed.get("link"):
                parsed["link"] = link
            parsed.setdefault("title", "Unknown Title")
            parsed.setdefault("description", "No description available")
            parsed.setdefault("location", "Unknown")
            job = JobExtracted(**parsed)
            logger.debug(f"Extracted: {job.title} at {job.company_name}")
            return job
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return None
