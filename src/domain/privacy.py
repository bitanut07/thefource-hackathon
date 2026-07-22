from collections.abc import Mapping

SENSITIVE_KEY_PARTS = ("authorization", "cookie", "secret", "token", "password")


def hash_user_id(user_id: str, salt: str) -> str:
    """Giữ contract băm UID trước khi ghi analytics hoặc audit."""
    # TODO: Chốt quản lý salt và triển khai HMAC cho UID.
    raise NotImplementedError("Chưa triển khai băm định danh người dùng")


def redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    """Giữ contract che dữ liệu nhạy cảm trước khi ghi log."""
    # TODO: Che token, secret, cookie và dữ liệu người dùng theo chính sách đã chốt.
    raise NotImplementedError("Chưa triển khai che dữ liệu nhạy cảm")
