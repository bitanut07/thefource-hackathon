import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from rq import Queue

from api import admin, admin_auth, catalog, health, intent, navigation, research, webhook
from api.admin_auth import AdminSessionStore
from config import Settings, get_settings
from domain.postgres_admin import PostgresAdminCatalog
from domain.postgres_registry import PostgresServiceRegistry
from domain.registry import JsonServiceRegistry, ServiceRegistryRepository
from domain.search import LaunchUrlPolicy
from llm.embeddings import GeminiEmbeddingClient
from skills.factory import build_navigator, parse_allowed_hosts


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
    database_url = (
        app_settings.database_url.get_secret_value().strip()
        if app_settings.database_url is not None
        else ""
    )
    if search_backend == "postgres":
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
    app.state.navigator = build_navigator(
        app_settings,
        registry=registry,
        url_policy=launch_url_policy,
    )
    app.state.admin_session_store = AdminSessionStore(
        redis_connection,
        ttl_seconds=app_settings.admin_session_ttl_seconds,
    )
    # The review console writes to the catalog, which only the PostgreSQL backend
    # supports. Leaving this unset makes its routes answer 503 instead of pretending
    # the JSON registry is editable.
    app.state.admin_catalog = (
        PostgresAdminCatalog(database_url, url_policy=launch_url_policy)
        if search_backend == "postgres"
        else None
    )

    allowed_origins = [
        origin.strip() for origin in app_settings.admin_allowed_origins.split(",") if origin.strip()
    ]
    if allowed_origins:
        # Only needed when the console calls this API straight from a browser. Serving
        # it through the admin app's own server keeps the session token off the client
        # and needs no CORS at all.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(navigation.router)
    app.include_router(intent.router)
    app.include_router(catalog.router)
    app.include_router(research.router)
    app.include_router(admin_auth.router)
    app.include_router(admin.router)
    return app


app = create_app()
