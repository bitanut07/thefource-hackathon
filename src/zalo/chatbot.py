"""Render navigator results using Zalo Chatbot's documented Dynamic API format."""

from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from llm.schemas import AgentResponse, ServiceChoice

ChatbotLayout = Literal["list", "buttons"]

_MAX_DYNAMIC_MESSAGES = 5
_MAX_LIST_ELEMENTS = 5
_OPEN_SERVICE_LABEL = "Mở dịch vụ"


def render_dynamic_response(
    response: AgentResponse,
    *,
    layout: ChatbotLayout = "list",
    image_urls: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build a Zalo Chatbot Format response.

    ``list`` is the closest documented match to a visual result list: it allows
    up to five elements, an optional HTTPS image on each element, and a URL
    action when the user taps an element.

    ``buttons`` provides an explicitly labelled URL button per result. Because
    Zalo documents a maximum of five messages in a Dynamic API response and the
    first message is the introduction, this layout returns at most four results.
    """

    if layout == "list":
        messages = _render_list_messages(response, image_urls or {})
    elif layout == "buttons":
        messages = _render_button_messages(response)
    else:
        raise ValueError(f"Unsupported Zalo Chatbot layout: {layout}")

    if len(messages) > _MAX_DYNAMIC_MESSAGES:
        raise AssertionError("Zalo Dynamic API response exceeds its documented message limit")
    return {"version": "chatbot", "content": {"messages": messages}}


def _render_list_messages(
    response: AgentResponse,
    image_urls: Mapping[str, str],
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"type": "text", "text": _intro_text(response)}]
    if not response.choices:
        return messages

    elements: list[dict[str, object]] = []
    for choice in response.choices[:_MAX_LIST_ELEMENTS]:
        element: dict[str, object] = {
            "title": choice.name,
            "subtitle": _subtitle(choice),
            "action": {"type": "url", "url": str(choice.launch_url)},
        }
        image_url = image_urls.get(str(choice.service_id))
        if image_url is None and choice.image_url is not None:
            image_url = str(choice.image_url)
        if image_url is not None:
            _validate_https_image_url(image_url)
            element["image_url"] = image_url
        elements.append(element)

    messages.append({"type": "list", "elements": elements})
    return messages


def _render_button_messages(response: AgentResponse) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"type": "text", "text": _intro_text(response)}]
    result_limit = _MAX_DYNAMIC_MESSAGES - 1
    for choice in response.choices[:result_limit]:
        messages.append(
            {
                "type": "text",
                "text": f"{choice.name}\n{_subtitle(choice)}",
                "buttons": [
                    {
                        "name": _OPEN_SERVICE_LABEL,
                        "type": "url",
                        # Zalo Chatbot's Dynamic API documents URL-button data
                        # under ``payload`` (not the OA OpenAPI ``url`` field).
                        "payload": str(choice.launch_url),
                    }
                ],
            }
        )
    return messages


def _intro_text(response: AgentResponse) -> str:
    parts = [response.message.strip()]
    clarification = (
        response.clarification_question.strip() if response.clarification_question else ""
    )
    if clarification and clarification != response.message.strip():
        parts.append(clarification)
    text = "\n".join(part for part in parts if part)
    return text or "Mình chưa tìm thấy dịch vụ phù hợp."


def _subtitle(choice: ServiceChoice) -> str:
    return choice.reason.strip() or "Mở dịch vụ để xem thông tin chi tiết."


def _validate_https_image_url(image_url: str) -> None:
    parsed = urlsplit(image_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Zalo Chatbot image_url must be an absolute HTTPS URL")
