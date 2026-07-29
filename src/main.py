import asyncio

from fastapi import FastAPI
from redis import Redis
from rq import Queue

from api import catalog, health, intent, navigation, research, stt, tts, webhook
from config import Settings, get_settings
from domain.postgres_registry import PostgresServiceRegistry
from domain.registry import JsonServiceRegistry, ServiceRegistryRepository
from domain.search import LaunchUrlPolicy
from llm.embeddings import GeminiEmbeddingClient
from skills.factory import build_navigator, parse_allowed_hosts
from voice.factory import build_stt_service, build_tts_service


def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo FastAPI app và các dependency của service navigator."""
    app_settings = settings or get_settings()
    is_production = app_settings.app_env.strip().casefold() == "production"
    docs_url = "/docs" if (not is_production or app_settings.enable_docs) else None
    app = FastAPI(
        title="Zalo AI Service Navigator",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=None,
    )
    redis_connection = Redis.from_url(
        app_settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    registry: ServiceRegistryRepository
    search_backend = app_settings.search_backend.strip().casefold()
    if search_backend == "postgres":
        database_url = (
            app_settings.database_url.get_secret_value().strip()
            if app_settings.database_url is not None
            else ""
        )
        registry = PostgresServiceRegistry(
            database_url,
            embedding_client=(
                GeminiEmbeddingClient(app_settings)
                if app_settings.semantic_search_enabled
                else None
            ),
        )
    elif search_backend == "json":
        registry = JsonServiceRegistry(app_settings.registry_data_path)
    else:
        raise ValueError("SEARCH_BACKEND chỉ hỗ trợ json hoặc postgres")
    launch_url_policy = LaunchUrlPolicy(parse_allowed_hosts(app_settings.allowed_launch_hosts))
    app.state.settings = app_settings
    app.state.redis_connection = redis_connection
    app.state.queue = Queue(app_settings.rq_queue_name, connection=redis_connection)
    app.state.registry = registry
    app.state.launch_url_policy = launch_url_policy
    app.state.navigator_semaphore = asyncio.Semaphore(app_settings.navigator_max_concurrency)
    app.state.tts_semaphore = asyncio.Semaphore(app_settings.tts_max_concurrency)
    app.state.stt_semaphore = asyncio.Semaphore(app_settings.stt_max_concurrency)
    app.state.navigator = build_navigator(
        app_settings,
        registry=registry,
        url_policy=launch_url_policy,
    )
    app.state.tts_service = build_tts_service(app_settings)
    app.state.stt_service = build_stt_service(app_settings)

    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(navigation.router)
    app.include_router(intent.router)
    app.include_router(catalog.router)
    app.include_router(research.router)
    app.include_router(tts.router)
    app.include_router(stt.router)
    return app


app = create_app()
