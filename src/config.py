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
    # ``chatbot_dynamic`` hands user-initiated replies to Zalo Chatbot Dynamic
    # API; the legacy OA webhook remains available during rollout.
    zalo_reply_mode: Literal["consultation", "chatbot_dynamic"] = "consultation"
    zalo_chatbot_token: SecretStr | None = None
    zalo_chatbot_timeout_seconds: float = Field(default=1.25, gt=0, le=1.8)
    zalo_chatbot_max_concurrency: int = Field(default=8, gt=0, le=64)
    zalo_chatbot_layout: Literal["list", "buttons"] = "list"

    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: SecretStr | None = None
    llm_timeout_seconds: int = Field(default=20, gt=0, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    navigator_api_key: SecretStr | None = None
    navigator_max_concurrency: int = Field(default=4, gt=0, le=64)
    navigator_queue_timeout_seconds: float = Field(default=0.1, gt=0, le=5)
    stt_provider: str = "disabled"
    stt_api_key: SecretStr | None = None

    allowed_launch_hosts: str = ""
    audio_retention_seconds: int = Field(default=900, gt=0)
    uid_hash_salt: SecretStr | None = None
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    """Tạo và cache cấu hình dùng trong bootstrap của từng process."""
    return Settings()
