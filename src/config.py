from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình tối thiểu, đọc từ biến môi trường hoặc tệp `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    enable_docs: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = ""
    registry_data_path: Path = Path("data/registry/services.real.json")
    rag_data_path: Path = Path("data/rag/service-catalog.sqlite3")
    database_url: SecretStr | None = None
    search_backend: str = "json"
    embedding_model: str = "gemini-embedding-001"
    # The initial pgvector index in db/migrations/001_service_catalog.sql uses vector(768).
    embedding_dimensions: int = Field(default=768, ge=768, le=768)
    semantic_search_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "zalo-navigator"

    zalo_api_base_url: str = ""
    zalo_app_id: str = ""
    zalo_oa_id: str = ""
    zalo_app_secret: SecretStr | None = None
    zalo_webhook_secret: SecretStr | None = None
    zalo_access_token: SecretStr | None = None
    zalo_refresh_token: SecretStr | None = None
    # Experimental legacy V2 list template. Keep disabled until a controlled
    # message to a test UID proves that the production OA still accepts it.
    zalo_list_template_enabled: bool = False
    zalo_list_image_url: str = ""

    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: SecretStr | None = None
    llm_timeout_seconds: int = Field(default=20, gt=0, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    navigator_api_key: SecretStr | None = None
    navigator_max_concurrency: int = Field(default=4, gt=0, le=64)
    navigator_queue_timeout_seconds: float = Field(default=0.1, gt=0, le=5)
    # Review console. Deliberately a separate credential from NAVIGATOR_API_KEY:
    # that key authorizes machine reads, this one authorizes catalog writes.
    admin_password: SecretStr | None = None
    admin_session_ttl_seconds: int = Field(default=43_200, ge=300, le=604_800)
    admin_login_max_attempts: int = Field(default=10, ge=3, le=100)
    admin_login_attempt_window_seconds: int = Field(default=900, ge=60, le=86_400)
    admin_allowed_origins: str = ""
    stt_provider: Literal["disabled", "gemini"] = "disabled"
    stt_api_key: SecretStr | None = None
    stt_model: str = "gemini-3.6-flash"
    stt_timeout_seconds: int = Field(default=20, gt=0, le=120)
    stt_max_retries: int = Field(default=1, ge=0, le=5)
    stt_max_concurrency: int = Field(default=2, gt=0, le=32)
    stt_queue_timeout_seconds: float = Field(default=0.1, gt=0, le=5)
    tts_provider: Literal["disabled", "gemini"] = "disabled"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_voice: str = "Kore"
    tts_timeout_seconds: int = Field(default=15, gt=0, le=120)
    tts_max_retries: int = Field(default=1, ge=0, le=5)
    tts_max_concurrency: int = Field(default=2, gt=0, le=32)
    tts_queue_timeout_seconds: float = Field(default=0.1, gt=0, le=5)

    allowed_launch_hosts: str = ""
    audio_retention_seconds: int = Field(default=900, gt=0)
    uid_hash_salt: SecretStr | None = None
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    """Tạo và cache cấu hình dùng trong bootstrap của từng process."""
    return Settings()
