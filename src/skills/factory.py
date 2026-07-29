from config import Settings
from domain.postgres_registry import PostgresServiceRegistry
from domain.registry import JsonServiceRegistry, ServiceRegistryRepository
from domain.search import LaunchUrlPolicy, SearchService
from llm.client import ConfiguredLLMClient
from llm.embeddings import GeminiEmbeddingClient
from llm.response import GeminiResponseComposer
from skills.navigator import NavigatorSkill


def parse_allowed_hosts(raw_hosts: str) -> frozenset[str]:
    """Parse the comma-separated launch URL allowlist from settings."""
    return frozenset(host.strip() for host in raw_hosts.split(",") if host.strip())


def build_navigator(
    settings: Settings,
    *,
    registry: ServiceRegistryRepository | None = None,
    url_policy: LaunchUrlPolicy | None = None,
) -> NavigatorSkill:
    """Build the controlled runtime pipeline from provider and registry settings."""
    if registry is not None:
        active_registry = registry
    elif settings.search_backend.strip().casefold() == "postgres":
        database_url = (
            settings.database_url.get_secret_value().strip()
            if settings.database_url is not None
            else ""
        )
        embedding_client = (
            GeminiEmbeddingClient(settings) if settings.semantic_search_enabled else None
        )
        active_registry = PostgresServiceRegistry(
            database_url,
            embedding_client=embedding_client,
        )
    else:
        active_registry = JsonServiceRegistry(settings.registry_data_path)
    active_url_policy = url_policy or LaunchUrlPolicy(
        parse_allowed_hosts(settings.allowed_launch_hosts)
    )
    search_service = SearchService(active_registry, active_url_policy)
    intent_extractor = ConfiguredLLMClient(settings)
    response_composer = GeminiResponseComposer(ConfiguredLLMClient(settings))
    return NavigatorSkill(intent_extractor, search_service, response_composer)
