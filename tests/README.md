# Kế hoạch kiểm thử

Hiện bộ khung chỉ chạy smoke test cho health endpoint và safety gate của webhook.

Các test nghiệp vụ cần bổ sung khi xử lý từng `# TODO`:

- contract webhook Zalo: chữ ký sai, event trùng và ACK sớm;
- registry JSON: schema, service `active`, ID trùng và URL ngoài allowlist;
- worker/Redis: enqueue, retry hữu hạn và failed job;
- text/voice: fake LLM, STT, Zalo client và luồng xác nhận transcript;
- evaluation: intent accuracy, slot F1, Recall@3, Top-1 và không bịa URL.

Không commit token OA, raw webhook production, audio hoặc transcript người dùng thật.
