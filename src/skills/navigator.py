from typing import Protocol

from domain.search import SearchService
from llm.schemas import AgentResponse, ServiceCandidate, StructuredQuery


class IntentExtractor(Protocol):
    async def extract_structured_query(self, text: str) -> StructuredQuery:
        """Extract a structured query from untrusted user text."""
        ...


class ResponseComposer(Protocol):
    async def compose(
        self,
        query: StructuredQuery,
        candidates: list[ServiceCandidate],
        *,
        text: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """Compose a response using only backend-provided candidates."""
        ...


class TemplateResponseComposer:
    """Deterministic response policy that never creates services or URLs."""

    async def compose(
        self,
        query: StructuredQuery,
        candidates: list[ServiceCandidate],
        *,
        text: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        del text, history
        if query.out_of_scope:
            return AgentResponse(
                message=(
                    "Mình chưa thể thực hiện yêu cầu này. "
                    "Mình có thể giúp bạn tìm dịch vụ y tế, điện - hóa đơn, "
                    "giáo dục, giao thông công cộng hoặc ăn uống."
                )
            )

        if query.needs_clarification:
            question = self._clarification_question(query.clarification_field)
            return AgentResponse(
                message=question,
                clarification_question=question,
            )

        safe_candidates = candidates[:5]
        if not safe_candidates:
            return AgentResponse(
                message=(
                    "Mình chưa tìm thấy dịch vụ phù hợp trong danh mục đã được kiểm chứng. "
                    "Bạn có thể thử nới điều kiện hoặc chọn một nhóm dịch vụ khác."
                )
            )

        return AgentResponse(
            message=(
                f"Mình tìm thấy {len(safe_candidates)} lựa chọn phù hợp "
                "trong danh mục đã được kiểm chứng."
            ),
            choices=[candidate.to_public_choice() for candidate in safe_candidates],
        )

    @staticmethod
    def _clarification_question(field: str | None) -> str:
        questions = {
            "service": "Bạn muốn tìm dịch vụ cụ thể nào?",
            "location": "Bạn muốn tìm dịch vụ ở khu vực nào?",
            "time": "Bạn cần sử dụng dịch vụ vào thời gian nào?",
            "target_user": "Dịch vụ này dành cho ai?",
            "organization": "Bạn đang cần dịch vụ cho công ty hoặc tổ chức nào?",
        }
        fallback = "Bạn có thể cho biết rõ hơn dịch vụ mình cần không?"
        return questions.get(field, fallback) if field is not None else fallback


class NavigatorSkill:
    intent_extractor: IntentExtractor
    search_service: SearchService
    response_composer: ResponseComposer

    def __init__(
        self,
        intent_extractor: IntentExtractor,
        search_service: SearchService,
        response_composer: ResponseComposer,
    ) -> None:
        self.intent_extractor = intent_extractor
        self.search_service = search_service
        self.response_composer = response_composer

    async def process_text(
        self,
        text: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        query = await self.intent_extractor.extract_structured_query(text)
        if query.out_of_scope or query.needs_clarification:
            return await self.response_composer.compose(query, [], text=text, history=history)

        candidates = await self.search_service.search(query, limit=5)
        return await self.response_composer.compose(
            query,
            candidates[:5],
            text=text,
            history=history,
        )
