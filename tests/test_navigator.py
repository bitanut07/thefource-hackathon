import asyncio
from uuid import UUID

import pytest
from pydantic import HttpUrl

from config import Settings
from domain.search import SearchService
from llm.client import ConfiguredLLMClient
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
        limit: int = 3,
    ) -> list[ServiceCandidate]:
        self.queries.append(query)
        self.limits.append(limit)
        return self.candidates


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


def _client(provider: str = "fake") -> ConfiguredLLMClient:
    return ConfiguredLLMClient(Settings(llm_provider=provider))


@pytest.mark.parametrize(
    ("text", "intent", "category", "service", "location", "time", "target_user"),
    [
        (
            "Tìm chỗ khám mắt ở Quận 5 cuối tuần.",
            "find_medical_service",
            "healthcare",
            "khám mắt",
            "Quận 5",
            "cuối tuần",
            None,
        ),
        (
            "Tôi muốn đóng tiền điện ở TP.HCM.",
            "pay_utility_bill",
            "utilities",
            "thanh toán tiền điện",
            "TP.HCM",
            None,
            None,
        ),
        (
            "mún tìm app học toán lớp năm cho cháu",
            "find_education_service",
            "education",
            "học toán",
            None,
            None,
            "grade_5_student",
        ),
        (
            "Tìm dịch vụ tra cứu tuyến xe đến bệnh viện.",
            "find_public_transport",
            "transport_public",
            "tra cứu tuyến xe",
            None,
            None,
            None,
        ),
    ],
)
def test_fake_provider_extracts_supported_vietnamese_queries(
    text: str,
    intent: str,
    category: str,
    service: str,
    location: str | None,
    time: str | None,
    target_user: str | None,
) -> None:
    query = asyncio.run(_client().extract_structured_query(text))

    assert query.intent == intent
    assert query.category == category
    assert query.service == service
    assert query.location == location
    assert query.time == time
    assert query.target_user == target_user
    assert query.needs_clarification is False
    assert query.out_of_scope is False


def test_ambiguous_education_query_requests_one_clarification() -> None:
    query = asyncio.run(_client().extract_structured_query("Tìm chỗ học cho cháu."))

    assert query.intent == "find_education_service"
    assert query.category == "education"
    assert query.service is None
    assert query.needs_clarification is True
    assert query.clarification_field == "service"
    assert query.out_of_scope is False


def test_action_request_is_out_of_scope() -> None:
    query = asyncio.run(_client().extract_structured_query("Đặt cho tôi vé máy bay sang Nhật."))

    assert query == StructuredQuery(intent="unknown", out_of_scope=True)


def test_non_fake_provider_fails_with_actionable_message() -> None:
    with pytest.raises(ValueError, match=r"LLM_PROVIDER=fake"):
        _client("unconfigured-provider")


def test_navigator_skips_search_for_clarification() -> None:
    search = StubSearchService([_candidate(1)])
    navigator = NavigatorSkill(_client(), search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tìm chỗ học cho cháu."))

    assert search.queries == []
    assert response.choices == []
    assert response.clarification_question == "Bạn muốn tìm dịch vụ cụ thể nào?"
    assert response.message == response.clarification_question


def test_navigator_skips_search_and_candidates_for_out_of_scope_request() -> None:
    search = StubSearchService([_candidate(1)])
    navigator = NavigatorSkill(_client(), search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Đặt cho tôi vé máy bay sang Nhật."))

    assert search.queries == []
    assert response.choices == []
    assert response.clarification_question is None
    assert "chưa thể thực hiện" in response.message


def test_navigator_returns_only_backend_candidates_and_limits_search() -> None:
    candidates = [_candidate(index) for index in range(1, 5)]
    search = StubSearchService(candidates)
    navigator = NavigatorSkill(_client(), search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tôi muốn đóng tiền điện ở TP.HCM."))

    assert search.limits == [3]
    assert search.queries[0].intent == "pay_utility_bill"
    assert response.choices == candidates[:3]
    assert len(response.choices) == 3
    assert str(response.choices[0].launch_url) == "https://example.com/services/1"


def test_navigator_no_result_does_not_invent_service_or_url() -> None:
    search = StubSearchService()
    navigator = NavigatorSkill(_client(), search, TemplateResponseComposer())

    response = asyncio.run(navigator.process_text("Tìm chỗ khám mắt ở Quận 5 cuối tuần."))

    assert len(search.queries) == 1
    assert response.choices == []
    assert "chưa tìm thấy" in response.message
    assert "http" not in response.message
