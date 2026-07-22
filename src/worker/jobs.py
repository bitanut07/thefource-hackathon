from collections.abc import Mapping


def process_message(payload: Mapping[str, object]) -> dict[str, object]:
    """Giữ entrypoint ổn định cho job xử lý text hoặc voice."""
    # TODO: Nối voice, LLM, registry, search, audit và Zalo theo workflow mục tiêu.
    raise NotImplementedError("Chưa triển khai job xử lý tin nhắn")
