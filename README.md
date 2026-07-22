# Zalo AI Service Navigator

Scaffold cho MVP trợ lý AI chạy dưới dạng Zalo Official Account (OA): người dùng nhập text hoặc gửi voice message, hệ thống hiểu nhu cầu, tìm/xếp hạng trong **Service Registry do nhóm kiểm soát** và trả tối đa ba dịch vụ hợp lệ.

> **Trạng thái:** khung khởi đầu cho hackathon, chưa phải tích hợp Zalo production. Endpoint/payload/signature/token lifecycle của Zalo, provider LLM/STT, danh mục dịch vụ thật và ngưỡng chất lượng vẫn cần được xác minh/chốt trước khi demo.

Các module hiện là skeleton: health endpoint chạy được, webhook chủ động trả `501`, còn worker, adapter và nghiệp vụ chính đều dừng ở chữ ký hàm với `# TODO`. Prompt trong `src/llm/prompts/` mới là policy draft, chưa chứng minh guardrail đã được load hoặc enforce ở runtime.

PDF kế hoạch gốc được giữ cục bộ tại `docs/Zalo_AI_Service_Navigator_Plan.pdf` và không commit lên GitHub. Tài liệu kỹ thuật đã tổng hợp nằm tại [docs/README.md](./docs/README.md).

## Phạm vi MVP

| Có trong MVP | Không thuộc MVP |
| --- | --- |
| Text và voice message trong Zalo OA | Gọi thoại thời gian thực/TTS |
| Intent + structured query + hỏi lại một câu | Tự do thao tác mọi màn hình Zalo |
| Tìm trong registry 20-40 dịch vụ đã kiểm chứng | Quét toàn bộ OA/Mini App công khai |
| Trả tối đa ba kết quả và CTA hợp lệ | Tự đặt lịch/thanh toán thay người dùng |
| URL lấy từ registry và allowlist | LLM tự tạo tên dịch vụ hoặc URL |
| Fallback/no-result và handoff rõ ràng | Broadcast/nhắn chủ động hàng loạt |

Stack hiện tại của bộ khung: **Python 3.12 + FastAPI + RQ/Redis + Service Registry JSON nạp vào bộ nhớ**. Zalo OA, LLM và STT nằm sau adapter để local/CI có thể dùng fake implementation khi các adapter đó được hoàn thiện, không cần credential thật. PostgreSQL/pgvector chỉ là phương án nâng cấp tương lai, không phải dependency của scaffold hackathon.

## Cấu trúc repository

```text
.
├── .github/                       # CI, Dependabot, issue/PR templates
├── data/
│   ├── evaluation/                # JSONL minh họa schema benchmark
│   └── seed/                      # 4 service giả, example.com, active=false
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
│   ├── voice/                      # Speech-to-Text và xử lý audio
│   ├── worker/                     # RQ jobs và worker entrypoint
│   ├── zalo/                       # Contract/client Zalo OA
│   ├── config.py                   # Cấu hình ứng dụng
│   └── main.py                     # FastAPI entrypoint
├── tests/                         # Smoke test hiện tại và kế hoạch test TODO
├── compose.yaml                   # API + worker + Redis
├── Dockerfile
├── Makefile
└── pyproject.toml
```

Chi tiết ranh giới và luồng xử lý nằm trong [architecture overview](./docs/architecture/overview.md). Tên module con có thể được bổ sung khi implement, nhưng code provider không được rò vào domain và response không được bypass candidate set của registry.

## Khởi động nhanh

Yêu cầu: Python 3.12, Docker có Compose plugin và Make.

```bash
make setup
.venv/bin/python -m pip install -e '.[dev]'
```

`make setup` chỉ tạo `.env` và `.venv`, không cài dependency. Giữ `LLM_PROVIDER=fake` và `STT_PROVIDER=fake` khi chưa có integration đã xác minh.

Ở terminal A:

```bash
make dev
```

Sau khi container sẵn sàng, kiểm tra ở terminal B:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
```

`POST /webhooks/zalo` hiện cố ý trả `501 ZALO_CONTRACT_NOT_CONFIGURED`. Đây là safety gate cho đến khi signature, event schema, acknowledgement và retry contract được xác minh bằng fixture/test chính thức.

`/health/ready` hiện cũng là scaffold response và chưa probe Redis; không dùng endpoint này làm production readiness gate cho đến khi dependency checks được triển khai.

Dừng local stack:

```bash
docker compose down
```

Scaffold không tự chạy `git init`, không tạo remote và không ghi credential. `make seed` hiện chỉ validate fixture; loader nạp registry JSON vào bộ nhớ vẫn là TODO.

## Lệnh thường dùng

| Command | Mục đích |
| --- | --- |
| `make help` | Liệt kê target |
| `make setup` | Tạo `.env`/`.venv`, không cài package |
| `.venv/bin/python -m pip install -e '.[dev]'` | Cài project và tool phát triển |
| `make dev` | Build/chạy API, worker và Redis |
| `make check PYTHON=.venv/bin/python` | Ruff format/lint + mypy + pytest |
| `make seed PYTHON=.venv/bin/python` | Validate seed JSON; chưa nạp vào runtime |
| `ALLOWED_LAUNCH_HOSTS=example.com .venv/bin/python scripts/verify_links.py --require-allowlist` | Kiểm tra tĩnh URL seed mẫu theo allowlist |
| `docker build -t zalo-service-navigator:local .` | Build image giống CI |
| `make tree` | In cây repo, bỏ generated files |

## Ánh xạ kiến trúc mục tiêu sang module

| Thành phần trong plan | Vị trí trong repo | Trách nhiệm |
| --- | --- | --- |
| Webhook Gateway | `src/api/`, `src/zalo/` | Parse/validate, signature, idempotency, enqueue, acknowledge sớm |
| Message Queue | `src/worker/`, Redis trong `compose.yaml` | RQ job, timeout, retry có giới hạn, failed-job handling |
| AI Agent Worker | `src/skills/`, `src/llm/` | Structured query, clarification, gọi search, response policy |
| Speech-to-Text | `src/voice/` | Tải tạm an toàn, STT, confidence flow, cleanup |
| Service Registry | `src/domain/registry.py`, `data/seed/` | Nạp JSON vào bộ nhớ; nguồn sự thật cho dịch vụ và URL |
| Search MVP | `src/domain/search.py` | Hard filter, chuẩn hóa, keyword/rule scoring và optional rerank |
| Query/Audit | `src/domain/audit.py`, `src/domain/privacy.py` | Dữ liệu debug tối thiểu, redaction và UID hash |
| OA OpenAPI | `src/zalo/` | Token, request formatting và error mapping sau khi contract được xác minh |
| Prompt policy | `src/llm/prompts/` | Extraction/response guardrails; không chứa secret hoặc service tự tạo |
| Evaluation/Demo/Ops | `data/evaluation/`, `docs/`, `.github/` | Benchmark, evidence, CI và runbook |

## Lộ trình 6 sprint

1. **OA Foundation** - chốt OA/App/quyền, xác minh webhook/send-message contract, text echo end-to-end, signature, idempotency, token adapter và health/logging.
2. **Registry** - chốt schema JSON, nhập 20-40 dịch vụ có owner, loader bộ nhớ, link verifier và example queries.
3. **Text Agent** - schema validation, hard filter + keyword/rule ranking/optional rerank, top 3, clarification, no-result/out-of-scope và URL allowlist.
4. **Voice Input** - audio event/download giới hạn, codec handling, STT tiếng Việt, confidence/confirmation và xóa audio tạm.
5. **UX & Operations** - greeting/menu/CTA, retry/failed jobs, fallback người thật, dashboard và runbook diễn tập.
6. **Evaluation** - bộ 100 query text/voice, benchmark metrics, hallucination guard, demo script và report gắn với commit/config.

Scaffold chỉ là nền móng của các sprint; file/thư mục tồn tại không đồng nghĩa deliverable đã nghiệm thu.

## Quyết định/TODO trước khi tích hợp thật

- [ ] OA và Zalo App nào dùng cho dev/demo? Loại OA, gói, quyền và owner là ai?
- [ ] Với từng text/voice event: URL tài liệu chính thức, event name, payload/attachment, acknowledgement, retry và signature contract hiện hành là gì?
- [ ] Endpoint/body/loại tin gửi phản hồi, access/refresh-token lifecycle, hạn mức và cửa sổ tương tác đã được contract-test chưa?
- [ ] Chọn provider LLM/model; chốt structured-output support, data processing/retention, timeout, quota/cost và fallback.
- [ ] Chọn provider STT tiếng Việt; chốt codec, giới hạn audio, confidence semantics, data region/retention và UX khi không có confidence.
- [ ] Chốt thời gian lưu audio/raw event/transcript/audit log, cơ chế xóa và UID hashing.
- [ ] Review/cấp owner cho 20-40 service thật; quyền công bố, allowlist và `last_verified_at` thế nào?
- [ ] Chốt ngưỡng Recall@3, Top-1, latency P95, STT success/confirm-again trước Sprint 6.
- [ ] Chọn LICENSE trước khi public; điền maintainer/security contact và GitHub team thật trước khi tạo CODEOWNERS.

Theo dõi chi tiết trong [Zalo integration checklist](./docs/integrations/zalo-checklist.md), [evaluation guide](./docs/evaluation/README.md) và [runbook](./docs/operations/runbook.md).

## Đóng góp và bảo mật

Đọc [CONTRIBUTING.md](./CONTRIBUTING.md) trước khi mở PR. Không đăng lỗ hổng, token hoặc dữ liệu người dùng qua issue công khai; xem [SECURITY.md](./SECURITY.md).

Repository cố ý chưa có `LICENSE` và `CODEOWNERS`: lựa chọn giấy phép và GitHub handle/team phải do owner thật quyết định, không dùng placeholder giả.
