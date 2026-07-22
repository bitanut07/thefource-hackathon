# Đóng góp cho Zalo AI Service Navigator

Cảm ơn bạn đã đóng góp. Đây là skeleton MVP: policy yêu cầu chỉ tìm trong Service Registry đã kiểm soát và không cho LLM tự tạo tên/URL, nhưng các guardrail/nghiệp vụ runtime vẫn là TODO. Không giả định contract Zalo chưa được xác minh.

## Chuẩn bị môi trường

Yêu cầu Python 3.12, Docker có Compose v2 plugin và Make.

```bash
make setup
.venv/bin/python -m pip install -e '.[dev]'
```

`make setup` chỉ tạo `.env`/`.venv`, không cài package. Giữ secret thật ngoài repository khi chạy `make dev`.

Ở terminal A:

```bash
make dev
```

Ở terminal B:

```bash
curl --fail http://localhost:8000/health/ready
```

Readiness hiện là stub, chưa probe Redis hoặc xác nhận registry JSON đã load. Health xanh không chứng minh luồng nghiệp vụ đã hoạt động.

## Quy trình thay đổi

1. Tạo branch ngắn, một mục tiêu rõ ràng.
2. Viết hoặc cập nhật test trước/đồng thời với thay đổi hành vi.
3. Giữ logic nghiệp vụ trong module domain/application; entrypoint chỉ wiring, adapter không rò SDK/provider vào domain.
4. Cập nhật tài liệu/ADR nếu thay đổi ranh giới, contract, persistence, queue hoặc guardrail.
5. Chạy kiểm tra bằng đúng virtual environment:

```bash
make check PYTHON=.venv/bin/python
PYTHONPYCACHEPREFIX=/tmp/zsn-ci-pycache .venv/bin/python -m compileall -q src tests scripts
make seed PYTHON=.venv/bin/python
ALLOWED_LAUNCH_HOSTS=example.com .venv/bin/python scripts/verify_links.py --require-allowlist
docker build -t zalo-service-navigator:local .
```

6. Mở PR theo template, nêu rõ command đã chạy, config/queue contract mới và rủi ro vận hành.

Không cần và không nên chạy `git init` trong các script setup của dự án. Việc tạo repository/remote thuộc quyền người sở hữu workspace.

## Quy ước code và test

- Python 3.12, type hints cho public boundary và I/O không tường minh.
- Ruff là formatter/linter; mypy là static type checker; pytest là test runner.
- Test không được gọi Zalo, LLM hoặc STT thật mặc định. Dùng fake adapter/fixture xác định sau khi chúng được triển khai.
- Mọi bug về duplicate event, URL hallucination, retention hoặc prompt injection cần regression test.
- Thay đổi queue payload/API/schema phải có versioning hoặc kế hoạch tương thích.
- Không “fix” test bằng cách nới guardrail registry/allowlist.

## Thay đổi Zalo integration

Endpoint, event name, payload, signature, token lifecycle và hạn mức phải được kiểm tra từ tài liệu chính thức tại thời điểm làm việc. PR cần:

- link trang chính thức chính xác và ngày kiểm tra;
- OA/App/quyền/phiên bản liên quan (không kèm credential);
- fixture đã loại UID, token, attachment URL và dữ liệu cá nhân;
- contract tests cho success, invalid signature/payload, duplicate và lỗi retryable;
- cập nhật [`docs/integrations/zalo-checklist.md`](./docs/integrations/zalo-checklist.md).

Không sao chép payload thật vào issue/PR để làm bằng chứng.

## Thay đổi Service Registry

- `data/seed/services.example.json` chỉ chứa dữ liệu giả, URL `example.com` và `active=false`.
- Service thật phải có owner, nguồn/xác minh link, `last_verified_at`, category/region/intent/alias đã review và policy allowlist.
- `make seed` hiện chỉ validate fixture; loader nạp JSON vào bộ nhớ vẫn là TODO.
- Không commit service thật ở trạng thái active nếu chưa có quyền công bố và quy trình review.
- Search/LLM/reranker không được bypass hard filter hoặc response candidate validation.

## Prompt và model

Prompt là code có ảnh hưởng bảo mật. PR thay prompt/provider/model cần nêu dataset/report, kiểm tra injection, no-result, clarification, out-of-scope và hallucination rate. Không commit prompt có secret, dữ liệu người dùng hoặc ví dụ chưa được phép sử dụng.

## Registry JSON và dữ liệu

- Registry thật dùng file JSON được review, 20-40 record, ID ổn định và schema version rõ.
- Thay đổi schema cần tương thích ngược hoặc có kế hoạch chuyển đổi/rollback file dữ liệu.
- Test loader với file hợp lệ, record lỗi, ID trùng, `active=false` và URL ngoài allowlist.
- Không đưa dump, raw event, audio thật, transcript nhạy cảm hoặc UID vào repository.

## Tài liệu quyết định

Thêm ADR mới trong `docs/decisions/` cho quyết định khó đảo ngược. Không xóa ADR cũ; đánh dấu `Superseded by ADR-XXXX` và liên kết quyết định thay thế.

Lỗ hổng hoặc nghi rò secret phải được báo riêng tư theo [SECURITY.md](./SECURITY.md), không tạo issue công khai.
