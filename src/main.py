from fastapi import FastAPI

from api import health, webhook
from config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo FastAPI app tối thiểu cho API process."""
    app_settings = settings or get_settings()
    docs_url = None if app_settings.app_env == "production" else "/docs"
    app = FastAPI(
        title="Zalo AI Service Navigator",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=None,
    )
    app.include_router(health.router)
    app.include_router(webhook.router)
    return app


app = create_app()
