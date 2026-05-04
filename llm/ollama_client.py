import httpx
from loguru import logger

from config.settings import EMBED_MODEL, OLLAMA_BASE_URL, OLLAMA_MODEL


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0)

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096,
            },
        }
        response = self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()["response"]

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        """Generate an embedding vector using /api/embed."""
        url = f"{self.base_url}/api/embed"
        payload = {"model": model or EMBED_MODEL, "input": text, "truncate": True}
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["embeddings"][0]
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def is_available(self) -> bool:
        try:
            resp = self.client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        self.client.close()
