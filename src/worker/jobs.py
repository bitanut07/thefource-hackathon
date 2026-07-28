import asyncio
from collections.abc import Mapping

from config import get_settings
from skills.factory import build_navigator
from zalo.client import ConfiguredZaloClient


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


def process_zalo_text_event(user_id: str, text: str, message_id: str) -> dict[str, object]:
    """Run the navigator off-webhook and reply to the originating OA user."""

    del message_id  # The id is used for ingress deduplication, never retained in a result.
    settings = get_settings()
    navigator = build_navigator(settings)
    response = asyncio.run(navigator.process_text(text))
    response_data = response.model_dump(mode="json")
    choices = response_data.get("choices", [])
    if not isinstance(choices, list):
        choices = []
    reply = _reply_text(response.message, choices)
    asyncio.run(ConfiguredZaloClient(settings).send_text(user_id, reply))
    return {"status": "sent", "choices": len(choices)}
