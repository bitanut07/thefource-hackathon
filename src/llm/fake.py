from dataclasses import dataclass

from llm.schemas import StructuredQuery


@dataclass(slots=True)
class FakeLLMClient:
    """Deterministic adapter kept only for tests, CI and offline fallback demos."""

    query: StructuredQuery

    async def extract_structured_query(self, text: str) -> StructuredQuery:
        del text
        return self.query.model_copy(deep=True)
