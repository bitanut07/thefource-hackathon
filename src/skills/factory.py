from config import Settings
from domain.registry import JsonServiceRegistry
from domain.search import LaunchUrlPolicy, SearchService
from llm.client import ConfiguredLLMClient
from skills.navigator import NavigatorSkill, TemplateResponseComposer


def parse_allowed_hosts(raw_hosts: str) -> frozenset[str]:
    """Parse the comma-separated launch URL allowlist from settings."""
    return frozenset(host.strip() for host in raw_hosts.split(",") if host.strip())


def build_navigator(settings: Settings) -> NavigatorSkill:
    """Build the deterministic local text pipeline from application settings."""
    registry = JsonServiceRegistry(settings.registry_data_path)
    url_policy = LaunchUrlPolicy(parse_allowed_hosts(settings.allowed_launch_hosts))
    search_service = SearchService(registry, url_policy)
    intent_extractor = ConfiguredLLMClient(settings)
    response_composer = TemplateResponseComposer()
    return NavigatorSkill(intent_extractor, search_service, response_composer)
