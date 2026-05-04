"""
LLM provider factory.

Pipelines call get_llm_client() and don't care whether it's Ollama or Vertex.
Switch by setting LLM_PROVIDER=ollama | vertex in .env (or environment).
"""
from loguru import logger

import config.settings as _cfg


def get_llm_client():
    provider = _cfg.LLM_PROVIDER.lower()

    if provider == "vertex":
        from llm.vertex_client import VertexClient
        logger.info(
            f"LLM provider: vertex "
            f"(gen={_cfg.VERTEX_GEN_MODEL}, embed={_cfg.VERTEX_EMBED_MODEL}@{_cfg.EMBED_DIM}d, "
            f"project={_cfg.GCP_PROJECT_ID}, region={_cfg.GCP_REGION})"
        )
        return VertexClient()

    if provider == "ollama":
        from llm.ollama_client import OllamaClient
        logger.info(
            f"LLM provider: ollama "
            f"(gen={_cfg.OLLAMA_MODEL}, embed={_cfg.EMBED_MODEL}, base={_cfg.OLLAMA_BASE_URL})"
        )
        return OllamaClient()

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Set LLM_PROVIDER=ollama or LLM_PROVIDER=vertex."
    )
