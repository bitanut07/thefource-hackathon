class STTUnavailableError(RuntimeError):
    """The configured speech-to-text provider cannot currently serve a request."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class STTProviderError(RuntimeError):
    """The provider failed or returned a transcript that cannot be used safely."""
