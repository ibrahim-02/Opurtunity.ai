import httpx
from loguru import logger

from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL


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

        data = response.json()
        return data["response"]

    def is_available(self) -> bool:
        try:
            resp = self.client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        self.client.close()
