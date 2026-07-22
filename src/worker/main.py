from redis import Redis
from rq import Queue, Worker

from config import get_settings


def main() -> None:
    """Khởi động RQ worker cho hàng đợi đã cấu hình."""
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.rq_queue_name, connection=connection)
    Worker([queue], connection=connection).work()


if __name__ == "__main__":
    main()
