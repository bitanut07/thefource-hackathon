import re

_CANONICAL_ZALO_OA_URL = re.compile(
    r"https://zalo\.me/[0-9]{10,25}",
    flags=re.ASCII,
)


def is_canonical_zalo_oa_url(value: str) -> bool:
    """Return whether ``value`` is a direct numeric Zalo OA deeplink."""

    return _CANONICAL_ZALO_OA_URL.fullmatch(value) is not None
