# Kế hoạch kiểm thử

Test hiện bao phủ:

- `POST /api/v1/navigate`: request validation, tối đa ba candidate, URL
  integrity và ánh xạ lỗi Gemini `502`/`503`;
- readiness: thiếu key, Registry/allowlist sai hoặc Redis lỗi trả `503`;
- API auth/concurrency: key sai trả `401`, hết slot xử lý trả `429`;
- Swagger inspection API: intent JSON, Registry list/detail và RAG
  `research_only` không làm lộ URL/metadata thô;
- webhook Zalo safety gate trả `501 ZALO_CONTRACT_NOT_CONFIGURED`;
- Gemini adapter/structured output qua gateway được inject, không gọi mạng thật;
- registry loader, 8 record trong `data/registry/services.real.json`, hard
  filter, ranking và URL allowlist;
- navigator/response policy, privacy/audit và knowledge-store guardrail.

Fake LLM adapter chỉ dùng trong unit test/CI và không thể chọn bằng cấu hình
runtime; đường chạy thật dùng Gemini và đọc key từ môi trường.

Các test tích hợp/evaluation vẫn cần bổ sung trước khi bật OA production:

- contract webhook Zalo: chữ ký sai, event trùng và ACK sớm;
- worker/Redis: retry hữu hạn, failed job và replay/idempotency;
- Zalo client: send-message, token refresh, rate limit và error mapping;
- Gemini staging smoke test: quota, timeout/retry và structured-output
  compatibility, chạy ngoài unit-test suite và không ghi request/secret;
- voice: STT provider, codec, confidence và luồng xác nhận transcript;
- evaluation trên mục tiêu 20-40 service: intent accuracy, slot F1, Recall@3,
  Top-1 và không bịa ID/URL.

Không commit token OA, raw webhook production, audio hoặc transcript người dùng thật.
