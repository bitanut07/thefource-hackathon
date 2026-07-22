# Đánh giá chất lượng MVP

Tài liệu này mô tả evaluation mục tiêu, chưa phải runner đã triển khai. Mục tiêu là đo toàn bộ chuỗi từ query đến candidate được chọn, không chỉ đánh giá câu văn của LLM. Bộ chính thức theo plan có 100 query; file [`data/evaluation/queries.example.jsonl`](../../data/evaluation/queries.example.jsonl) chỉ minh họa schema và không phải benchmark đủ đại diện.

## Cấu trúc dataset

Mỗi dòng JSONL là một test case độc lập:

```json
{
  "id": "eval-text-001",
  "modality": "text",
  "query": "Tìm chỗ khám mắt ở Quận 5 cuối tuần.",
  "expected": {
    "intent": "find_medical_service",
    "category": "healthcare",
    "service_ids": ["00000000-0000-4000-8000-000000000001"],
    "needs_clarification": false,
    "out_of_scope": false
  },
  "tags": ["canonical", "location", "time"]
}
```

- `service_ids` là tập đáp án chấp nhận được, không hàm ý mọi ID phải xuất hiện.
- Test voice có thể dùng `audio_fixture` trỏ tới fixture không chứa dữ liệu cá nhân; `query` là transcript chuẩn để tính WER/slot.
- Case thiếu dữ liệu có `needs_clarification=true` và không bắt buộc service ID.
- Case ngoài phạm vi có `out_of_scope=true`; hệ thống không được giả vờ đã thực hiện hành động.
- Dataset thật phải dùng service ID của registry đã review và được version cùng report.

## Phân tầng test

| Tầng | Mục đích |
| --- | --- |
| Unit | Normalization, hard filter, scoring, URL policy, prompt/schema guard |
| Contract | Zalo envelope/signature và provider adapter bằng fixture đã xác minh |
| Integration | Redis/RQ, loader registry JSON và idempotency |
| End-to-end | Luồng dự kiến text/voice -> queue -> result/fallback với fake provider sau khi được triển khai |
| Offline evaluation | Chạy toàn bộ dataset, xuất metrics theo commit/config/model |

## Chỉ số đánh giá

- **Intent accuracy**: tỷ lệ query có intent đúng.
- **Slot extraction F1**: micro/macro F1 cho category, location, time, target user và slot nghiệp vụ.
- **Recall@3**: tỷ lệ query có ít nhất một service ID chấp nhận được trong top 3.
- **Top-1 accuracy**: tỷ lệ candidate đầu tiên thuộc tập đáp án.
- **Hallucination rate**: tỷ lệ tên/ID/URL trong phản hồi không thuộc candidate set backend cung cấp; mục tiêu bắt buộc là 0.
- **Clarification/no-result rate**: báo cáo theo nhóm query, không tối ưu một con số tổng làm mất safety.
- **Latency**: median/P95 end-to-end và theo stage STT, LLM, search, OA adapter.
- **Voice**: transcription success, WER khi có ground truth, confirm-again và voice-to-result conversion.

Ngưỡng pass cho Recall@3, Top-1, latency và voice chưa được plan chốt. Owner phải ghi ngưỡng, dataset version và lý do trước Sprint 6; CI không được âm thầm chọn một số tùy ý.

## Chạy kiểm tra

```bash
make check PYTHON=.venv/bin/python
```

Runner evaluation là TODO của Sprint 6; `scripts/run_evaluation.py` chưa tồn tại trong skeleton nên chưa có lệnh benchmark đầy đủ để chạy. Khi triển khai, report cần ghi commit SHA, thời gian, dataset hash/version, registry snapshot, provider/model, prompt version hoặc content hash, cấu hình ranking và số lượng lỗi/skip.

## Quy tắc dữ liệu

- Không đưa raw UID, audio người dùng thật hoặc transcript nhạy cảm vào Git.
- Dữ liệu giọng nói cần consent/license và quy trình retention rõ ràng.
- Tách development set khỏi holdout set; không sửa đáp án chỉ để khớp output hiện tại.
- Review lỗi theo persona/category/accent/noise, không chỉ nhìn metric tổng.
- Sample service trong repo đều `active=false`, nên test production-like phải dùng snapshot registry riêng đã xác minh.
