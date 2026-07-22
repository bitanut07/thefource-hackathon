from functools import lru_cache
from pathlib import Path

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
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = ""
    registry_data_path: Path = Path("data/seed/services.example.json")
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "zalo-navigator"

    zalo_api_base_url: str = ""
    zalo_app_id: str = ""
    zalo_oa_id: str = ""
    zalo_app_secret: SecretStr | None = None
    zalo_webhook_secret: SecretStr | None = None
    zalo_access_token: SecretStr | None = None
    zalo_refresh_token: SecretStr | None = None

    llm_provider: str = "fake"
    llm_model: str = ""
    llm_api_key: SecretStr | None = None
    stt_provider: str = "fake"
    stt_api_key: SecretStr | None = None

    allowed_launch_hosts: str = ""
    audio_retention_seconds: int = Field(default=900, gt=0)
    uid_hash_salt: SecretStr | None = None
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    """Tạo và cache cấu hình dùng trong bootstrap của từng process."""
    return Settings()
