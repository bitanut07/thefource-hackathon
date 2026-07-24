import asyncio
from collections.abc import Mapping

from config import get_settings
from skills.factory import build_navigator


def process_message(payload: Mapping[str, object]) -> dict[str, object]:
    """Process a text message through the same pipeline as the navigation API."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Job payload phải có trường text không rỗng.")

    navigator = build_navigator(get_settings())
    response = asyncio.run(navigator.process_text(text))
    return response.model_dump(mode="json")
