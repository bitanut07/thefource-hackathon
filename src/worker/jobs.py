import asyncio
import logging
from collections.abc import Mapping
from typing import Protocol

from config import get_settings
from domain.conversation import ConversationStore
from skills.factory import build_navigator
from zalo.client import ConfiguredZaloClient, ZaloAPIError, ZaloListElement

logger = logging.getLogger(__name__)


class ZaloReplySender(Protocol):
    async def send_list(
        self,
        user_id: str,
        text: str,
        elements: list[ZaloListElement],
    ) -> None: ...

    async def send_text(self, user_id: str, text: str) -> None: ...


def process_message(payload: Mapping[str, object]) -> dict[str, object]:
    """Process a text message through the same pipeline as the navigation API."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Job payload phải có trường text không rỗng.")

    navigator = build_navigator(get_settings())
    response = asyncio.run(navigator.process_text(text))
    return response.model_dump(mode="json")


def _reply_text(message: str, choices: list[dict[str, object]]) -> str:
    """Render a compact, plaintext Zalo consultation reply."""

    lines = [message.strip()]
    if choices:
        lines.append("Gợi ý phù hợp:")
        for number, choice in enumerate(choices, start=1):
            name = choice.get("name")
            launch_url = choice.get("launch_url")
            if isinstance(name, str) and isinstance(launch_url, str):
                lines.append(f"{number}. {name}\n{launch_url}")
    return "\n".join(line for line in lines if line).strip()


def _list_elements(
    choices: list[dict[str, object]],
    *,
    image_url: str = "",
) -> list[ZaloListElement]:
    elements: list[ZaloListElement] = []
    for choice in choices[:5]:
        name = choice.get("name")
        reason = choice.get("reason")
        launch_url = choice.get("launch_url")
        avatar_url = choice.get("avatar_url")
        if not isinstance(name, str) or not isinstance(launch_url, str):
            continue
        elements.append(
            ZaloListElement(
                title=name,
                subtitle=reason
                if isinstance(reason, str) and reason.strip()
                else "Dịch vụ phù hợp",
                url=launch_url,
                image_url=(
                    avatar_url if isinstance(avatar_url, str) and avatar_url.strip() else image_url
                ),
            )
        )
    return elements


async def _send_navigation_response(
    client: ZaloReplySender,
    user_id: str,
    message: str,
    choices: list[dict[str, object]],
    *,
    list_template_enabled: bool,
    list_image_url: str = "",
) -> str:
    """Prefer one text-plus-list message and preserve the V3 plaintext fallback."""

    elements = _list_elements(choices, image_url=list_image_url) if list_template_enabled else []
    if elements:
        try:
            await client.send_list(user_id, message, elements)
            return "list"
        except (ValueError, ZaloAPIError) as exc:
            logger.warning("Zalo list template unavailable; using V3 text fallback: %s", exc)

    await client.send_text(user_id, _reply_text(message, choices))
    return "text"


def process_zalo_text_event(user_id: str, text: str, message_id: str) -> dict[str, object]:
    """Run the navigator off-webhook and reply to the originating OA user."""

    del message_id  # The id is used for ingress deduplication, never retained in a result.
    settings = get_settings()
    navigator = build_navigator(settings)
    from redis import Redis

    conversations = ConversationStore(Redis.from_url(settings.redis_url))
    response = asyncio.run(navigator.process_text(text, history=conversations.history(user_id)))
    response_data = response.model_dump(mode="json")
    choices = response_data.get("choices", [])
    if not isinstance(choices, list):
        choices = []
    delivery = asyncio.run(
        _send_navigation_response(
            ConfiguredZaloClient(settings),
            user_id,
            response.message,
            choices,
            list_template_enabled=settings.zalo_list_template_enabled,
            list_image_url=settings.zalo_list_image_url.strip(),
        )
    )
    conversations.append(user_id, "user", text)
    conversations.append(user_id, "assistant", response.message)
    return {"status": "sent", "delivery": delivery, "choices": len(choices)}
