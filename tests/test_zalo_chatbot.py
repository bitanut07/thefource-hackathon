from uuid import UUID

import pytest

from llm.schemas import AgentResponse, ServiceChoice
from zalo.chatbot import render_dynamic_response

SERVICE_ID = UUID("f48f7026-e2e2-41bd-a788-49470153e7e8")


def _response(choice_count: int = 1) -> AgentResponse:
    choices = [
        ServiceChoice(
            service_id=UUID(int=SERVICE_ID.int + index),
            name=f"Dịch vụ {index + 1}",
            service_type="website",
            launch_url=f"https://example.com/service-{index + 1}",
            region="VN",
            reason=f"Phù hợp với nhu cầu {index + 1}.",
        )
        for index in range(choice_count)
    ]
    return AgentResponse(message="Các dịch vụ phù hợp:", choices=choices)


def test_dynamic_list_has_image_and_clickable_url_action() -> None:
    payload = render_dynamic_response(
        _response(),
        image_urls={str(SERVICE_ID): "https://cdn.example.com/logo.png"},
    )

    assert payload == {
        "version": "chatbot",
        "content": {
            "messages": [
                {"type": "text", "text": "Các dịch vụ phù hợp:"},
                {
                    "type": "list",
                    "elements": [
                        {
                            "title": "Dịch vụ 1",
                            "subtitle": "Phù hợp với nhu cầu 1.",
                            "image_url": "https://cdn.example.com/logo.png",
                            "action": {
                                "type": "url",
                                "url": "https://example.com/service-1",
                            },
                        }
                    ],
                },
            ]
        },
    }


def test_dynamic_list_limits_results_to_five() -> None:
    payload = render_dynamic_response(_response(choice_count=5))
    content = payload["content"]

    assert isinstance(content, dict)
    messages = content["messages"]
    assert isinstance(messages, list)
    result_list = messages[1]
    assert isinstance(result_list, dict)
    elements = result_list["elements"]
    assert isinstance(elements, list)
    assert len(elements) == 5


def test_explicit_button_layout_uses_at_most_five_messages() -> None:
    payload = render_dynamic_response(_response(choice_count=5), layout="buttons")
    content = payload["content"]

    assert isinstance(content, dict)
    messages = content["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 5
    first_result = messages[1]
    assert isinstance(first_result, dict)
    assert first_result["buttons"] == [
        {
            "name": "Mở dịch vụ",
            "type": "url",
            "url": "https://example.com/service-1",
        }
    ]


def test_dynamic_response_rejects_non_https_image() -> None:
    with pytest.raises(ValueError, match="absolute HTTPS"):
        render_dynamic_response(
            _response(),
            image_urls={str(SERVICE_ID): "http://cdn.example.com/logo.png"},
        )


def test_empty_response_is_still_valid_chatbot_text() -> None:
    payload = render_dynamic_response(
        AgentResponse(
            message="",
            clarification_question="Bạn cần dịch vụ ở khu vực nào?",
        )
    )

    assert payload == {
        "version": "chatbot",
        "content": {
            "messages": [
                {"type": "text", "text": "Bạn cần dịch vụ ở khu vực nào?"},
            ]
        },
    }


def test_clarification_question_is_not_duplicated() -> None:
    question = "Bạn cần dịch vụ ở khu vực nào?"

    payload = render_dynamic_response(
        AgentResponse(message=question, clarification_question=question)
    )

    assert payload == {
        "version": "chatbot",
        "content": {"messages": [{"type": "text", "text": question}]},
    }
