from __future__ import annotations

from typing import Protocol

import httpx
from google import genai
from google.genai import errors, types

from config import Settings
from llm.client import LLMProviderError, LLMUnavailableError


class EmbeddingClient(Protocol):
    async def embed_query(self, text: str) -> tuple[float, ...]:
        """Create a bounded semantic-search query vector."""
        ...


class GeminiEmbeddingClient:
    """Gemini embedding adapter used only for the controlled service catalog."""

    def __init__(self, settings: Settings) -> None:
        api_key = (
            settings.gemini_api_key.get_secret_value().strip()
            if settings.gemini_api_key is not None
            else ""
        )
        if not api_key:
            raise LLMUnavailableError("Gemini chưa được cấu hình để tạo embedding.")
        self._api_key = api_key
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._timeout_seconds = settings.llm_timeout_seconds

    async def embed_query(self, text: str) -> tuple[float, ...]:
        try:
            client = genai.Client(
                api_key=self._api_key,
                http_options={"api_version": "v1"},
            )
            async with client.aio as async_client:
                response = await async_client.models.embed_content(
                    model=self._model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=self._dimensions,
                    ),
                )
        except errors.APIError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise LLMUnavailableError("Gemini embedding tạm thời không sẵn sàng.") from exc
            raise LLMProviderError(f"Gemini embedding trả lỗi {exc.code}.") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError("Không thể kết nối Gemini embedding.") from exc

        embeddings = response.embeddings or []
        values = embeddings[0].values if embeddings else None
        if values is None or len(values) != self._dimensions:
            raise LLMProviderError("Gemini embedding trả vector không đúng kích thước.")
        return tuple(float(value) for value in values)
