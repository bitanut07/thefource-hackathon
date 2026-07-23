# Kế hoạch kiểm thử

Test hiện bao phủ health/webhook safety gate, registry loader/search/URL policy,
fake intent extraction, navigator/response policy, privacy/audit và API demo.

Các test tích hợp thật vẫn cần bổ sung khi kết nối provider/OA:

- contract webhook Zalo: chữ ký sai, event trùng và ACK sớm;
- worker/Redis: retry hữu hạn, failed job và replay/idempotency;
- Zalo client: send-message, token refresh, rate limit và error mapping;
- voice: STT provider, codec, confidence và luồng xác nhận transcript;
- evaluation: intent accuracy, slot F1, Recall@3, Top-1 và không bịa URL.

Không commit token OA, raw webhook production, audio hoặc transcript người dùng thật.
