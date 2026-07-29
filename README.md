# FOne — AI Service Navigator

**FOne** là dự án hackathon do đội gồm **4 thành viên** phát triển. Đây là trợ lý
AI chạy trên Zalo Official Account (OA), giúp người dùng diễn đạt nhu cầu tự nhiên
và tìm đúng **Zalo OA hoặc Mini App đã được xác minh** trong Service Catalog.

FOne không phải công cụ tìm kiếm Internet và không tự tạo link, tên dịch vụ hay
thông tin nhà cung cấp. Gemini chỉ hiểu/trích xuất nhu cầu và diễn đạt câu trả
lời; backend mới là nơi lọc, xếp hạng và quyết định candidate được phép gửi ra.

> **Trạng thái:** production nhận sự kiện text từ Zalo OA qua webhook, xử lý bất
> đồng bộ bằng worker, tìm trên PostgreSQL Service Catalog và trả lời qua OA API.
> Swagger vẫn có API để kiểm tra intent, catalog và toàn bộ luồng navigation.

PDF kế hoạch gốc được giữ cục bộ tại `docs/Zalo_AI_Service_Navigator_Plan.pdf` và không commit lên GitHub. Tài liệu kỹ thuật đã tổng hợp nằm tại [docs/README.md](./docs/README.md).

## Phạm vi MVP

| Có trong MVP | Không thuộc MVP |
| --- | --- |
| Text webhook Zalo OA; API STT/TTS theo yêu cầu | Nhận/gửi voice message qua Zalo OA hoặc gọi thoại thời gian thực |
| Intent + structured query + hỏi lại một câu | Tự do thao tác mọi màn hình Zalo |
| Tìm trong registry 20-40 dịch vụ đã kiểm chứng | Quét toàn bộ OA/Mini App công khai |
| Trả tối đa năm kết quả và CTA hợp lệ | Tự đặt lịch/thanh toán thay người dùng |
| URL lấy từ registry và allowlist | LLM tự tạo tên dịch vụ hoặc URL |
| Fallback/no-result và handoff rõ ràng | Broadcast/nhắn chủ động hàng loạt |

Stack hiện tại: **Python 3.12 + FastAPI + Gemini + RQ/Redis +
PostgreSQL/pgvector**. Zalo OA, LLM, STT và TTS nằm sau adapter; test/CI dùng
implementation deterministic được inject và không cần credential thật.

## Cấu trúc repository

```text
.
├── .github/                       # CI, Dependabot, issue/PR templates
├── data/
│   ├── evaluation/                # JSONL minh họa schema benchmark
│   ├── registry/                  # Registry runtime đã review
│   ├── research/                  # Evidence/candidate; không tự động publish
│   └── seed/                      # Fixture kiểm thử, không dùng ở runtime thật
├── docs/
│   ├── architecture/              # Kiến trúc và dependency boundaries
│   ├── decisions/                 # ADR cho quyết định khó đảo ngược
│   ├── demo/                      # Kịch bản và checklist demo
│   ├── evaluation/                # Metric/dataset protocol
│   ├── integrations/              # Checklist contract Zalo
│   └── operations/                # Runbook
├── scripts/                       # Bootstrap/check/seed/link verification
├── src/                            # Cấu trúc phẳng, mỗi thư mục một trách nhiệm
│   ├── api/                        # Health và webhook routes
│   ├── domain/                     # Model, registry, search, audit và privacy
│   ├── llm/                        # Schema, client và prompt LLM
│   ├── skills/                     # Điều phối luồng Service Navigator
│   ├── voice/                      # Speech-to-Text, Text-to-Speech và audio
│   ├── worker/                     # RQ jobs và worker entrypoint
│   ├── zalo/                       # Contract/client Zalo OA
│   ├── config.py                   # Cấu hình ứng dụng
│   └── main.py                     # FastAPI entrypoint
├── tests/                         # Unit/integration tests không gọi provider thật
├── compose.yaml                   # API + worker + Redis
├── Dockerfile
├── Makefile
└── pyproject.toml
```

Chi tiết ranh giới và luồng xử lý nằm trong [architecture overview](./docs/architecture/overview.md). Tên module con có thể được bổ sung khi implement, nhưng code provider không được rò vào domain và response không được bypass candidate set của registry.

## Khởi động nhanh

Yêu cầu: Python 3.12, uv 0.11.19, Docker có Compose plugin và Make.

```bash
make setup
uv sync --locked --extra dev --link-mode copy
```

`make setup` chỉ tạo `.env` và `.venv`, không cài dependency. Trong `.env`, giữ
`LLM_PROVIDER=gemini` và đặt một key mới, chưa từng công khai:

```dotenv
GEMINI_API_KEY=your-rotated-key
NAVIGATOR_API_KEY=your-separate-random-api-key-at-least-16-characters
```

Không commit key. Nếu một key từng được gửi qua chat, log, issue hoặc commit, hãy
thu hồi/rotate key đó trước khi dùng.

Khởi động stack bằng Make:

```bash
make dev
```

Trên Windows/PowerShell, có thể dùng Compose trực tiếp thay cho `make setup` và
`make dev`:

```powershell
Copy-Item .env.example .env
uv sync --locked --extra dev --link-mode copy
# Mở .env, đặt GEMINI_API_KEY mới đã rotate và một NAVIGATOR_API_KEY riêng.
docker compose up --build -d
```

Sau khi container sẵn sàng, kiểm tra ở terminal khác:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
```

`/health/live` chỉ kiểm tra process. `/health/ready` trả `200` khi hai key đã
được cấu hình, Registry có record hoạt động, allowlist bao phủ toàn bộ URL đang
hoạt động và Redis sẵn sàng; cấu hình thiếu/sai hoặc mất Redis trả `503`.
Registry được validate fail-fast khi API dựng pipeline lúc khởi động.

`POST /webhooks/zalo` hiện cố ý trả `501 ZALO_CONTRACT_NOT_CONFIGURED`. Đây là
safety gate cho đến khi signature, event schema, acknowledgement, retry và
send-message contract được xác minh bằng fixture/test chính thức.

### Gọi API điều hướng text

Mở Swagger tại `http://localhost:8000/docs`, bấm **Authorize**, nhập
`NAVIGATOR_API_KEY` từ `.env`, sau đó dùng các API:

| API | Dùng để kiểm tra |
| --- | --- |
| `POST /api/v1/intents/extract` | JSON intent Gemini đã trích xuất và validate |
| `GET /api/v1/services` | Danh sách Registry active, URL đã qua allowlist |
| `GET /api/v1/services/{service_id}` | Chi tiết một dịch vụ runtime |
| `POST /api/v1/research/search` | Dữ liệu crawl/RAG ở chế độ `research_only`, không URL/CTA |
| `POST /api/v1/navigate` | Toàn bộ flow và tối đa năm service card |
| `POST /api/v1/stt` | Audio nhị phân thành transcript tiếng Việt |
| `POST /api/v1/tts` | Lời đáp và tên dịch vụ thành WAV tiếng Việt |
| `GET /health/live`, `GET /health/ready` | Trạng thái process và dependency |

Ví dụ cho API điều hướng:

```json
{
  "text": "Tôi muốn đóng tiền điện ở TP.HCM."
}
```

Hoặc gọi bằng PowerShell:

```powershell
$body = @{ text = "Tìm chỗ khám mắt ở Quận 5." } | ConvertTo-Json
$navigatorApiKey = Read-Host "Nhập NAVIGATOR_API_KEY từ .env"
$headers = @{ "X-API-Key" = $navigatorApiKey }
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/navigate `
  -Headers $headers `
  -ContentType application/json `
  -Body $body
```

Endpoint gọi Gemini đồng bộ để hiểu câu hỏi, sau đó backend lọc và xếp hạng
`data/registry/services.real.json`. Gemini không được tạo service ID hoặc URL;
response builder chỉ trả tối đa năm candidate từ Registry. Thiếu cấu hình key
làm endpoint trả `503`, key truy cập sai trả `401`, hết slot xử lý trả `429`,
và lỗi provider hoặc structured output không hợp lệ trả `502`.

### Gọi API Speech-to-Text và Text-to-Speech

Hai endpoint voice mặc định bị tắt và dùng chung `X-API-Key` với API điều hướng.
Để bật Gemini trong `.env`:

```dotenv
STT_PROVIDER=gemini
TTS_PROVIDER=gemini
```

STT nhận trực tiếp audio nhị phân WAV, MP3, AIFF, AAC, OGG hoặc FLAC, tối đa
10 MiB. Ví dụ:

```bash
curl --fail \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -H "Content-Type: audio/wav" \
  --data-binary @sample.wav \
  http://localhost:8000/api/v1/stt
```

TTS chỉ đọc `message` và tối đa năm `choice_names`, không nhận URL. Response là
WAV mono 24 kHz, 16-bit và bị giới hạn 5 MiB:

```bash
curl --fail \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"Mình tìm thấy ba lựa chọn phù hợp.","choice_names":["EVNHCMC","ZaloPay","MoMo"]}' \
  --output /tmp/fone-response.wav \
  http://localhost:8000/api/v1/tts
```

Audio và transcript chỉ được xử lý trong bộ nhớ, không lưu vào disk, Redis hoặc
database. Phiên bản này chưa nhận/gửi voice message qua Zalo và không tự sinh
audio cho mọi response điều hướng.

### Kho RAG nghiên cứu

Dữ liệu crawl/research có thể được dựng thành SQLite để tra cứu nội bộ:

```powershell
uv run python scripts\build_rag_db.py
```

Lệnh tạo `data/rag/service-catalog.sqlite3` (file sinh, không commit). Hiện kho
này có 88 tài liệu knowledge staging: 83 dịch vụ nghiên cứu và 5 tài liệu
context/pending, gồm cả dữ liệu VNG Campus chưa xác minh. Báo cáo batch 29 OA
mới nằm tại `docs/research/additional-oa-2026-07-24.md`; batch 21 OA nhà hàng,
đồ ăn và đồ uống nằm tại
`docs/research/additional-food-oa-2026-07-24.md`.
Swagger cho phép tra cứu qua `POST /api/v1/research/search`, nhưng endpoint luôn
gắn `usage=research_only` và không trả URL/metadata thô. Kho này **không tham gia
luồng `/api/v1/navigate`** và không có quyền sinh CTA; Registry thật + URL
allowlist vẫn là nguồn duy nhất cho candidate có thể mở.

Với dịch vụ `service_type=oa`, CTA phải là deeplink số chính chủ theo đúng dạng
`https://zalo.me/<OA_ID>`. Slug, `oa.zalo.me/...`, Mini App `/s/...`, query,
fragment và dấu `/` cuối đều không được phép xuất hiện trong response runtime.

Dừng local stack:

```bash
docker compose down
```

Scaffold không tự chạy `git init`, không tạo remote và không ghi credential.
`make seed` validate registry thật mặc định nhưng không ghi dữ liệu. Runtime đọc
`data/registry/services.real.json` qua `REGISTRY_DATA_PATH`; 8 record hiện tại
không thay cho mục tiêu review đủ 20-40 dịch vụ trước demo OA.

## Lệnh thường dùng

| Command | Mục đích |
| --- | --- |
| `make help` | Liệt kê target |
| `make setup` | Tạo `.env`/`.venv`, không cài package |
| `uv sync --locked --extra dev --link-mode copy` | Cài đúng dependency từ `uv.lock` |
| `make dev` | Build/chạy API, worker và Redis |
| `make check PYTHON=.venv/bin/python` | Ruff format/lint + mypy + pytest |
| `make seed PYTHON=.venv/bin/python` | Validate registry thật mặc định, không ghi dữ liệu |
| `.venv/bin/python scripts/seed_registry.py --file data/registry/services.real.json` | Validate tối thiểu 8 record runtime, không ghi dữ liệu |
| `ALLOWED_LAUNCH_HOSTS=zalo.me .venv/bin/python scripts/verify_links.py --file data/registry/services.real.json --require-allowlist` | Kiểm tra tĩnh URL registry thật theo allowlist và bắt buộc OA dùng deeplink số; không gọi mạng |
| `.venv/bin/python scripts/build_rag_db.py` | Dựng SQLite knowledge staging; chưa nối runtime và không cấp quyền tạo CTA |
| `docker build -t zalo-service-navigator:local .` | Build image giống CI |
| `make tree` | In cây repo, bỏ generated files |

## Ánh xạ kiến trúc mục tiêu sang module

| Thành phần trong plan | Vị trí trong repo | Trách nhiệm |
| --- | --- | --- |
| Webhook Gateway | `src/api/`, `src/zalo/` | Parse/validate, signature, idempotency, enqueue, acknowledge sớm |
| Message Queue | `src/worker/`, Redis trong `compose.yaml` | RQ job, timeout, retry có giới hạn, failed-job handling |
| AI Agent Worker | `src/skills/`, `src/llm/` | Structured query, clarification, gọi search, response policy |
| Speech I/O | `src/voice/` | STT/TTS theo yêu cầu, giới hạn audio, provider adapter và không lưu dữ liệu |
| Service Registry | `src/domain/registry.py`, `data/registry/services.real.json` | Nạp JSON vào bộ nhớ; nguồn sự thật cho dịch vụ và URL |
| Search MVP | `src/domain/search.py` | Hard filter, chuẩn hóa, keyword/rule scoring và optional rerank |
| Query/Audit | `src/domain/audit.py`, `src/domain/privacy.py` | Dữ liệu debug tối thiểu, redaction và UID hash |
| OA OpenAPI | `src/zalo/` | Token, request formatting và error mapping sau khi contract được xác minh |
| Prompt policy | `src/llm/prompts/` | Extraction/response guardrails; không chứa secret hoặc service tự tạo |
| Evaluation/Demo/Ops | `data/evaluation/`, `docs/`, `.github/` | Benchmark, evidence, CI và runbook |

## Lộ trình 6 sprint

1. **OA Foundation** - chốt OA/App/quyền, xác minh webhook/send-message contract, text echo end-to-end, signature, idempotency, token adapter và health/logging.
2. **Registry** - chốt schema JSON, nhập 20-40 dịch vụ có owner, loader bộ nhớ, link verifier và example queries.
3. **Text Agent** - schema validation, hard filter + keyword/rule ranking/optional rerank, top 5, clarification, no-result/out-of-scope và URL allowlist.
4. **Voice Input** - API STT/TTS độc lập đã có; audio event/download từ Zalo, confidence/confirmation và gửi voice vẫn cần contract riêng.
5. **UX & Operations** - greeting/menu/CTA, retry/failed jobs, fallback người thật, dashboard và runbook diễn tập.
6. **Evaluation** - bộ 100 query text/voice, benchmark metrics, hallucination guard, demo script và report gắn với commit/config.

Scaffold chỉ là nền móng của các sprint; file/thư mục tồn tại không đồng nghĩa deliverable đã nghiệm thu.

## Quyết định/TODO trước khi tích hợp thật

- [ ] OA và Zalo App nào dùng cho dev/demo? Loại OA, gói, quyền và owner là ai?
- [ ] Với từng text/voice event: URL tài liệu chính thức, event name, payload/attachment, acknowledgement, retry và signature contract hiện hành là gì?
- [ ] Endpoint/body/loại tin gửi phản hồi, access/refresh-token lifecycle, hạn mức và cửa sổ tương tác đã được contract-test chưa?
- [ ] Gemini/model đã chọn cho runtime; cần chốt data processing/retention, quota/cost, ngưỡng timeout/retry và fallback vận hành.
- [ ] Xác nhận Gemini STT/TTS quota, data processing/region và UX khi transcript không có confidence trước khi nối voice event Zalo.
- [ ] Chốt thời gian lưu audio/raw event/transcript/audit log, cơ chế xóa và UID hashing.
- [ ] Review/cấp owner cho 20-40 service thật; quyền công bố, allowlist và `last_verified_at` thế nào?
- [ ] Chốt ngưỡng Recall@3, Top-1, latency P95, STT success/confirm-again trước Sprint 6.
- [ ] Chọn LICENSE trước khi public; điền maintainer/security contact và GitHub team thật trước khi tạo CODEOWNERS.

Theo dõi chi tiết trong [Zalo integration checklist](./docs/integrations/zalo-checklist.md), [evaluation guide](./docs/evaluation/README.md) và [runbook](./docs/operations/runbook.md).

## Đóng góp và bảo mật

Đọc [CONTRIBUTING.md](./CONTRIBUTING.md) trước khi mở PR. Không đăng lỗ hổng, token hoặc dữ liệu người dùng qua issue công khai; xem [SECURITY.md](./SECURITY.md).

Repository cố ý chưa có `LICENSE` và `CODEOWNERS`: lựa chọn giấy phép và GitHub handle/team phải do owner thật quyết định, không dùng placeholder giả.
