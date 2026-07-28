# PostgreSQL Hybrid Service Search

## Mục tiêu

PostgreSQL là Service Catalog runtime khi `SEARCH_BACKEND=postgres`. JSON vẫn là
nguồn import/fixture; OA research không tự động được publish.

```text
JSON Registry + OA candidates
        -> seed_postgres.py
        -> PostgreSQL Service Catalog
        -> FTS + pg_trgm + pgvector/RRF
        -> /api/v1/navigate
```

## Quyền publish

Chỉ row có đồng thời `active=true` và `review_status` là `approved` hoặc
`published` được `PostgresServiceRegistry` materialize thành service runtime.
`candidate` từ crawl luôn được import với `active=false`; chúng không thể sinh
CTA hoặc xuất hiện tại `/navigate`.

## Search

1. Gemini trích xuất `StructuredQuery`; không tạo OA ID hay URL.
2. PostgreSQL tạo ba danh sách candidate: FTS (`tsvector`), typo/alias
   (`pg_trgm`) và semantic similarity (`pgvector`) khi embedding đã được seed.
3. Repository gộp thứ hạng bằng Reciprocal Rank Fusion (RRF), cộng boost nhỏ
   cho category/priority.
4. `SearchService` áp URL allowlist và response policy trước khi serialize.

Khi `SEMANTIC_SEARCH_ENABLED=false`, semantic lane bị tắt; FTS + alias/trigram
vẫn chạy. Chỉ bật sau khi đã tạo vector bằng `make catalog-embed`.

## Vận hành

```powershell
$env:DATABASE_URL='postgresql://navigator:...@localhost:5432/navigator'
make catalog-migrate
make catalog-seed
# Có GEMINI_API_KEY đã rotate và muốn semantic search:
make catalog-embed
```

Compose khởi tạo extension `vector` và `pg_trgm` từ
`db/migrations/001_service_catalog.sql`. Docker data volume chỉ nên dùng cho
môi trường phát triển; production phải đặt `POSTGRES_PASSWORD` và
`DATABASE_URL` qua secret manager.
