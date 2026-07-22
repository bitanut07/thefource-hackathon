from pathlib import Path
from typing import Protocol
from uuid import UUID

from domain.models import RegistryService
from llm.schemas import StructuredQuery


class ServiceRegistryRepository(Protocol):
    async def get_active(self, service_id: UUID) -> RegistryService | None:
        # TODO: Đọc một dịch vụ đang hoạt động từ registry JSON trong bộ nhớ.
        raise NotImplementedError("Chưa triển khai đọc dịch vụ từ registry")

    async def search(self, query: StructuredQuery, limit: int = 10) -> list[RegistryService]:
        # TODO: Tìm dịch vụ theo truy vấn có cấu trúc và các bộ lọc bắt buộc.
        raise NotImplementedError("Chưa triển khai tìm kiếm trong registry")


class JsonServiceRegistry:
    """Registry JSON được thiết kế để nạp một lần vào bộ nhớ."""

    path: Path

    def __init__(self, path: Path) -> None:
        # TODO: Nạp và kiểm tra registry JSON vào bộ nhớ khi khởi tạo.
        raise NotImplementedError("Chưa triển khai khởi tạo registry JSON")

    async def get_active(self, service_id: UUID) -> RegistryService | None:
        # TODO: Lấy dịch vụ đang hoạt động theo định danh từ registry bộ nhớ.
        raise NotImplementedError("Chưa triển khai đọc dịch vụ đang hoạt động")

    async def search(self, query: StructuredQuery, limit: int = 10) -> list[RegistryService]:
        # TODO: Lọc registry bộ nhớ theo truy vấn và giới hạn kết quả.
        raise NotImplementedError("Chưa triển khai tìm kiếm registry JSON")
