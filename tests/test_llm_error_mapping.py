"""Provider failures must reach callers as the documented contract.

The SDK raises two unrelated exception trees depending on the call path, and the
gateway used to catch only one of them. Everything it missed escaped as an unhandled
500 with a traceback, and the bounded retry never ran. These tests pin the mapping so
that regression cannot come back silently.
"""

from typing import Any

import httpx
import pytest
from google.genai import errors

from llm.client import (
    GoogleGenAIGateway,
    LLMProviderError,
    LLMUnavailableError,
    _provider_retry_after,
    _provider_status_code,
)

pytest.importorskip("google.genai._gaos.lib.compat_errors")
from google.genai._gaos.lib import compat_errors as compat  # noqa: E402

# The SDK's private compat module declares no public exports, so strict mode rejects
# reading these directly. Aliased once here rather than ignoring at every use.
NoResponseError = compat.NoResponseError  # type: ignore[attr-defined]
ResponseValidationError = compat.ResponseValidationError  # type: ignore[attr-defined]


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        headers=headers or {},
        request=httpx.Request("POST", "https://example.invalid/interactions"),
    )


def _gateway(monkeypatch: pytest.MonkeyPatch, failure: BaseException) -> GoogleGenAIGateway:
    """A gateway whose single provider call always raises ``failure``."""

    gateway = GoogleGenAIGateway("test-key", timeout_seconds=5, max_retries=1)

    async def always_fail(**_kwargs: Any) -> str:
        raise failure

    monkeypatch.setattr(gateway, "_generate_once", always_fail)
    monkeypatch.setattr("llm.client.asyncio.sleep", _no_sleep)
    return gateway


async def _no_sleep(_seconds: float) -> None:
    return None


async def _run(gateway: GoogleGenAIGateway) -> str:
    return await gateway.generate_json(
        model="gemini-3.5-flash-lite",
        user_input="tôi cần đóng tiền điện",
        system_instruction="test",
        schema={"type": "object"},
    )


def test_the_two_sdk_error_trees_really_are_unrelated() -> None:
    """Guards the assumption the fix exists for.

    If a future SDK unifies these, catching both stays harmless — but if this ever
    fails, the duplicated handling can be simplified.
    """

    assert not issubclass(compat.RateLimitError, errors.APIError)
    assert not issubclass(errors.UnknownApiResponseError, errors.APIError)


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            compat.RateLimitError("quota exceeded", response=_response(429), body=None),
            id="interactions-429",
        ),
        pytest.param(
            compat.InternalServerError("boom", response=_response(500), body=None),
            id="interactions-500",
        ),
        # The classic tree takes the status as its first positional argument.
        pytest.param(
            errors.APIError(429, {"error": {"message": "rate limited"}}),
            id="classic-429",
        ),
    ],
)
def test_retriable_provider_failures_become_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    import asyncio

    gateway = _gateway(monkeypatch, failure)

    with pytest.raises(LLMUnavailableError) as caught:
        asyncio.run(_run(gateway))
    # api.security maps this to 503 + Retry-After rather than a 500.
    assert caught.value.retry_after_seconds is not None


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            compat.BadRequestError("bad request", response=_response(400), body=None),
            id="interactions-400",
        ),
        pytest.param(
            compat.AuthenticationError("no key", response=_response(401), body=None),
            id="interactions-401",
        ),
        pytest.param(
            errors.APIError(400, {"error": {"message": "bad request"}}),
            id="classic-400",
        ),
    ],
)
def test_non_retriable_provider_failures_become_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    import asyncio

    gateway = _gateway(monkeypatch, failure)

    with pytest.raises(LLMProviderError):
        asyncio.run(_run(gateway))


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(NoResponseError("empty"), id="no-response"),
        pytest.param(
            ResponseValidationError(
                "unreadable",
                raw_response=_response(200),
                cause=ValueError("bad json"),
            ),
            id="response-validation",
        ),
        pytest.param(
            compat.APIResponseValidationError(response=_response(200), body=None),
            id="api-response-validation",
        ),
        pytest.param(
            errors.UnknownApiResponseError("unreadable"),
            id="classic-unknown-response",
        ),
    ],
)
def test_malformed_responses_are_not_retried_and_map_to_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    import asyncio

    gateway = _gateway(monkeypatch, failure)

    with pytest.raises(LLMProviderError):
        asyncio.run(_run(gateway))


def test_connection_failures_are_retried_then_reported_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    request = httpx.Request("POST", "https://example.invalid/interactions")
    gateway = _gateway(monkeypatch, compat.APIConnectionError(message="down", request=request))

    with pytest.raises(LLMUnavailableError):
        asyncio.run(_run(gateway))


def test_status_code_is_read_from_either_tree() -> None:
    assert _provider_status_code(errors.APIError(503, {})) == 503
    assert (
        _provider_status_code(compat.RateLimitError("x", response=_response(429), body=None)) == 429
    )
    assert _provider_status_code(NoResponseError("x")) is None


def test_retry_after_prefers_the_provider_hint() -> None:
    # Advertising one second when the provider asked for six sends the client
    # straight back into the same wall.
    with_hint = compat.RateLimitError(
        "quota", response=_response(429, {"retry-after": "6"}), body=None
    )
    assert _provider_retry_after(with_hint) == 6
    assert _provider_retry_after(NoResponseError("x")) == 1
    unparsable = compat.RateLimitError(
        "quota", response=_response(429, {"retry-after": "soon"}), body=None
    )
    assert _provider_retry_after(unparsable) == 1
