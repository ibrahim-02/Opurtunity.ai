"""
Vertex AI client with the same interface as OllamaClient:
- generate(prompt) -> str  (Gemini, JSON mode for structured output)
- embed(text)      -> list[float]  (gemini-embedding-001 truncated to EMBED_DIM)
- is_available()   -> bool

Auth picks up GOOGLE_APPLICATION_CREDENTIALS from the environment, or falls
back to the gcp-key.json path set in config.settings.GCS_KEY_PATH.
"""
import os

from google import genai
from google.genai import types
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import config.settings as _cfg


class VertexClient:
    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        gen_model: str | None = None,
        embed_model: str | None = None,
        embed_dim: int | None = None,
    ):
        self.project = project or _cfg.GCP_PROJECT_ID
        self.location = location or _cfg.GCP_REGION
        self.gen_model = gen_model or _cfg.VERTEX_GEN_MODEL
        self.embed_model = embed_model or _cfg.VERTEX_EMBED_MODEL
        self.embed_dim = embed_dim or _cfg.EMBED_DIM

        if not self.project:
            raise RuntimeError("GCP_PROJECT_ID is not set in environment / .env")

        # ensure auth credentials are discoverable
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and _cfg.GCS_KEY_PATH:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _cfg.GCS_KEY_PATH

        self._client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def generate(self, prompt: str) -> str:
        """Return the model's text response. JSON mode + low temperature."""
        response = self._client.models.generate_content(
            model=self.gen_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        return response.text or ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """Return a single embedding vector at self.embed_dim dimensions."""
        try:
            result = self._client.models.embed_content(
                model=model or self.embed_model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.embed_dim,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            return list(result.embeddings[0].values)
        except Exception as e:
            logger.error(f"Vertex embedding failed: {e}")
            return None

    def is_available(self) -> bool:
        """Probe with a 1-char embed call to verify auth + region + model."""
        try:
            v = self.embed("ok")
            return bool(v) and len(v) == self.embed_dim
        except Exception as e:
            logger.warning(f"Vertex availability check failed: {e}")
            return False

    def close(self):
        # google-genai client doesn't require explicit cleanup
        pass
