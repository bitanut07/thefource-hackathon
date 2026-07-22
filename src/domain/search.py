from dataclasses import dataclass

from domain.registry import ServiceRegistryRepository
from llm.schemas import ServiceCandidate, StructuredQuery

SEMANTIC_WEIGHT = 0.40
INTENT_WEIGHT = 0.30
LOCATION_WEIGHT = 0.15
KEYWORD_WEIGHT = 0.10
PRIORITY_WEIGHT = 0.05


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    semantic_similarity: float
    intent_match: float
    location_match: float
    keyword_match: float
    service_priority: float


def final_score(components: ScoreComponents) -> float:
    # TODO: Chuẩn hóa từng thành phần và áp dụng trọng số đã được nghiệm thu.
    raise NotImplementedError("Chưa triển khai công thức xếp hạng dịch vụ")


class LaunchUrlPolicy:
    allowed_hosts: frozenset[str]

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        # TODO: Chuẩn hóa allowlist host dùng để kiểm tra URL khởi chạy.
        raise NotImplementedError("Chưa triển khai chính sách URL khởi chạy")

    def is_allowed(self, url: str) -> bool:
        # TODO: Kiểm tra scheme và host của URL theo allowlist đã cấu hình.
        raise NotImplementedError("Chưa triển khai kiểm tra URL khởi chạy")


class SearchService:
    registry: ServiceRegistryRepository
    url_policy: LaunchUrlPolicy

    def __init__(
        self,
        registry: ServiceRegistryRepository,
        url_policy: LaunchUrlPolicy,
    ) -> None:
        # TODO: Gắn registry và chính sách URL cho pipeline tìm kiếm.
        raise NotImplementedError("Chưa triển khai khởi tạo dịch vụ tìm kiếm")

    async def search(self, query: StructuredQuery, limit: int = 3) -> list[ServiceCandidate]:
        # TODO: Lọc cứng, xếp hạng và kiểm tra URL trước khi tạo candidate.
        raise NotImplementedError("Chưa triển khai tìm kiếm và xếp hạng dịch vụ")
