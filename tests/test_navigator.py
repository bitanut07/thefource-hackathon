import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from google.genai import errors
from pydantic import HttpUrl, SecretStr

from config import Settings
from domain.search import SearchService
from llm.client import (
    SYSTEM_INSTRUCTION,
    ConfiguredLLMClient,
    GoogleGenAIGateway,
    LLMProviderError,
    LLMUnavailableError,
)
from llm.fake import FakeLLMClient
from llm.schemas import ServiceCandidate, StructuredQuery
from skills.navigator import NavigatorSkill, TemplateResponseComposer


class StubSearchService(SearchService):
    candidates: list[ServiceCandidate]
    queries: list[StructuredQuery]
    limits: list[int]

    def __init__(self, candidates: list[ServiceCandidate] | None = None) -> None:
        self.candidates = candidates or []
        self.queries = []
        self.limits = []

    async def search(
        self,
        query: StructuredQuery,
        limit: int = 5,
    ) -> list[ServiceCandidate]:
        self.queries.append(query)
        self.limits.append(limit)
        return self.candidates


class StubStructuredGateway:
    output_text: str
    calls: list[dict[str, object]]

    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls = []

    async def generate_json(
        self,
        *,
        model: str,
        user_input: str,
        system_instruction: str,
        schema: dict[str, Any],
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "user_input": user_input,
                "system_instruction": system_instruction,
                "schema": schema,
            }
        )
        return self.output_text


class FailingGoogleGateway(GoogleGenAIGateway):
    def __init__(self, error: Exception, *, max_retries: int) -> None:
        super().__init__("test-only", timeout_seconds=1, max_retries=max_retries)
        self.error = error
        self.attempts = 0

    async def _generate_once(
        self,
        *,
        model: str,
        user_input: str,
        system_instruction: str,
        schema: dict[str, Any],
    ) -> str:
        del model, user_input, system_instruction, schema
        self.attempts += 1
        raise self.error


def _candidate(index: int) -> ServiceCandidate:
    return ServiceCandidate(
        service_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
        name=f"Dịch vụ kiểm thử {index}",
        service_type="website",
        launch_url=HttpUrl(f"https://example.com/services/{index}"),
        region="TP.HCM",
        reason="Phù hợp với truy vấn kiểm thử.",
        score=1 - (index / 10),
    )


def _configured_client(
    query: StructuredQuery,
) -> tuple[ConfiguredLLMClient, StubStructuredGateway]:
    gateway = StubStructuredGateway(query.model_dump_json())
    settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-3.5-flash-lite",
        gemini_api_key=SecretStr("test-only"),
    )
    return ConfiguredLLMClient(settings, gateway=gateway), gateway


def test_gemini_adapter_requests_structured_output_and_validates_response() -> None:
    expected = StructuredQuery(
        intent="find_food_service",
        category="shopping",
        service="đồ ăn",
        target_user="vng_employee",
        organization="VNG",
    )
    client, gateway = _configured_client(expected)

    query = asyncio.run(client.extract_structured_query("Là nhân viên VNG hiện tôi cần mua đồ ăn."))

    assert query == expected
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["model"] == "gemini-3.5-flash-lite"
    assert gateway.calls[0]["user_input"] == "Là nhân viên VNG hiện tôi cần mua đồ ăn."
    schema = gateway.calls[0]["schema"]
    assert isinstance(schema, dict)
    assert schema["additionalProperties"] is False
    assert "organization" in schema["properties"]
    assert schema["properties"]["service"]["description"]
    assert "<untrusted_input>" in SYSTEM_INSTRUCTION
    assert "Không hỏi lại location" in SYSTEM_INSTRUCTION
    assert "không tự tạo mã nội bộ" in SYSTEM_INSTRUCTION


def test_gemini_adapter_rejects_invalid_provider_json() -> None:
    gateway = StubStructuredGateway('{"intent":"x","category":"not-supported"}')
    client = ConfiguredLLMClient(
        Settings(llm_provider="gemini", gemini_api_key=SecretStr("test-only")),
        gateway=gateway,
    )

    with pytest.raises(LLMProviderError, match="không vượt qua schema"):
        asyncio.run(client.extract_structured_query("query"))


def test_missing_gemini_key_fails_only_when_serving_a_query() -> None:
    client = ConfiguredLLMClient(
        Settings(llm_provider="gemini", gemini_api_key=None),
    )

    with pytest.raises(LLMUnavailableError, match="GEMINI_API_KEY"):
        asyncio.run(client.extract_structured_query("Tìm dịch vụ"))


def test_gemini_gateway_bounds_transport_retries_and_maps_unknown_responses() -> None:
    transport_gateway = FailingGoogleGateway(
        httpx.ConnectError("offline"),
        max_retries=1,
    )
    with pytest.raises(LLMUnavailableError, match="kết nối") as transport_error:
        asyncio.run(
            transport_gateway.generate_json(
                model="gemini-3.5-flash-lite",
                user_input="query",
                system_instruction="instruction",
                schema={"type": "object"},
            )
        )
    assert transport_gateway.attempts == 2
    assert transport_error.value.retry_after_seconds == 1

    unknown_gateway = FailingGoogleGateway(
        errors.UnknownApiResponseError("invalid"),
        max_retries=3,
    )
    with pytest.raises(LLMProviderError, match="không thể đọc"):
        asyncio.run(
            unknown_gateway.generate_json(
                model="gemini-3.5-flash-lite",
                user_input="query",
                system_instruction="instruction",
                schema={"type": "object"},
            )
        )
    assert unknown_gateway.attempts == 1

    quota_gateway = FailingGoogleGateway(
        errors.ClientError(
            429,
            {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        ),
        max_retries=0,
    )
    with pytest.raises(LLMUnavailableError) as quota_error:
        asyncio.run(
            quota_gateway.generate_json(
                model="gemini-3.5-flash-lite",
                user_input="query",
                system_instruction="instruction",
                schema={"type": "object"},
            )
        )
    assert quota_error.value.retry_after_seconds == 1


def test_non_gemini_runtime_provider_fails_with_actionable_message() -> None:
    with pytest.raises(ValueError, match=r"LLM_PROVIDER=gemini"):
        ConfiguredLLMClient(Settings(llm_provider="fake"))


def test_navigator_skips_search_for_clarification() -> None:
    search = StubSearchService([_candidate(1)])
    extractor = FakeLLMClient(
        StructuredQuery(
            intent="find_education_service",
            category="education",
            needs_clarification=True,
            clarification_field="service",
        )
    )
    navigator = NavigatorSkill(extractor, search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tìm chỗ học cho cháu."))

    assert search.queries == []
    assert response.choices == []
    assert response.clarification_question == "Bạn muốn tìm dịch vụ cụ thể nào?"
    assert response.message == response.clarification_question


def test_navigator_asks_the_specific_organization_clarification() -> None:
    search = StubSearchService()
    extractor = FakeLLMClient(
        StructuredQuery(
            intent="find_food_service",
            category="shopping",
            needs_clarification=True,
            clarification_field="organization",
        )
    )
    navigator = NavigatorSkill(extractor, search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tìm chỗ ăn cho nhân viên công ty."))

    assert search.queries == []
    assert response.clarification_question == ("Bạn đang cần dịch vụ cho công ty hoặc tổ chức nào?")


def test_navigator_skips_search_and_candidates_for_out_of_scope_request() -> None:
    search = StubSearchService([_candidate(1)])
    extractor = FakeLLMClient(StructuredQuery(intent="unknown", out_of_scope=True))
    navigator = NavigatorSkill(extractor, search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Đặt cho tôi vé máy bay sang Nhật."))

    assert search.queries == []
    assert response.choices == []
    assert response.clarification_question is None
    assert "chưa thể thực hiện" in response.message


def test_navigator_returns_only_backend_candidates_and_limits_search() -> None:
    candidates = [_candidate(index) for index in range(1, 7)]
    search = StubSearchService(candidates)
    extractor = FakeLLMClient(
        StructuredQuery(
            intent="pay_utility_bill",
            category="utilities",
            service="thanh toán tiền điện",
            location="TP.HCM",
        )
    )
    navigator = NavigatorSkill(extractor, search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tôi muốn đóng tiền điện ở TP.HCM."))

    assert search.limits == [5]
    assert search.queries[0].intent == "pay_utility_bill"
    assert len(response.choices) == 5
    assert [choice.service_id for choice in response.choices] == [
        candidate.service_id for candidate in candidates[:5]
    ]
    assert str(response.choices[0].launch_url) == "https://example.com/services/1"
    assert "score" not in response.model_dump_json()


def test_navigator_no_result_does_not_invent_service_or_url() -> None:
    search = StubSearchService()
    extractor = FakeLLMClient(
        StructuredQuery(
            intent="find_medical_service",
            category="health",
            service="khám mắt",
            location="Quận 5",
            time="cuối tuần",
        )
    )
    navigator = NavigatorSkill(extractor, search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tìm chỗ khám mắt ở Quận 5 cuối tuần."))

    assert len(search.queries) == 1
    assert response.choices == []
    assert "chưa tìm thấy" in response.message
    assert "http" not in response.message
