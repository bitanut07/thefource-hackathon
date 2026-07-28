from config import Settings
from domain.registry import JsonServiceRegistry, ServiceRegistryRepository
from domain.search import LaunchUrlPolicy, SearchService
from llm.client import ConfiguredLLMClient
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
    active_registry: ServiceRegistryRepository = registry or JsonServiceRegistry(
        settings.registry_data_path
    )
    active_url_policy = url_policy or LaunchUrlPolicy(
        parse_allowed_hosts(settings.allowed_launch_hosts)
    )
    search_service = SearchService(active_registry, active_url_policy)
    intent_extractor = ConfiguredLLMClient(settings)
    response_composer = GeminiResponseComposer(ConfiguredLLMClient(settings))
    return NavigatorSkill(intent_extractor, search_service, response_composer)
