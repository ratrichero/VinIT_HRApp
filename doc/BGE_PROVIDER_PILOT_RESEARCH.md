# Khảo sát provider BGE-M3 cho pilot

**Phạm vi:** khảo sát tài liệu công khai; sau đó anh tự chạy một request thử trên máy của anh và báo kết quả. Agent không nhận credential, không trực tiếp gọi API. Định hướng: ưu tiên Cloudflare Workers AI BGE-M3 cho pilot bằng dữ liệu tổng hợp sau khi chốt account/quota và scope, không mặc định đưa vào production. Thông tin giá/điều khoản có thể đổi; xác minh theo account và hợp đồng trước khi trả phí hoặc gửi CV thật.

### Kết quả smoke test do anh thực hiện

Anh báo `Kết quả: PASS; số chiều: 1024` khi gọi endpoint OpenAI-compatible với model `@cf/baai/bge-m3` và một câu thử synthetic. Script đã kiểm tra độ dài 1024 và từng phần tử hữu hạn. Đây là **kết quả do người vận hành báo lại**, không có log độc lập; không lưu Account ID/token. Chỉ chứng minh request đơn lẻ theo phạm vi script, chưa chứng minh batch/order, cache, giới hạn, latency, chất lượng retrieval, privacy hoặc runtime môi trường đích. Chưa đóng DEP-05/06.

| Ứng viên | Bằng chứng công khai | Hạn chế/chưa xác minh |
|---|---|---|
| Cloudflare Workers AI | Tài liệu model công bố `@cf/baai/bge-m3`, Cloudflare-hosted, zero data retention và hỗ trợ `/v1/embeddings` [1](https://developers.cloudflare.com/workers-ai/models/bge-m3/). AI Search liệt kê model này 1024 chiều [2](https://developers.cloudflare.com/ai-search/configuration/models/supported-models/). Trang giá Workers AI ghi 10.000 Neurons/ngày free và BGE-M3 1.075 Neurons/triệu input tokens, giá tương đương $0,012/triệu token [3](https://developers.cloudflare.com/workers-ai/platform/pricing/). Người vận hành báo một request synthetic trả vector 1024 chiều hữu hạn. | Chưa xác minh batch/order, instruction, giới hạn input, quota/region tại account; trang AI Search là giới hạn của sản phẩm AI Search, không tự suy là giới hạn chung API. Zero data retention của model không thay DPA/retention gateway, log, egress, data residency hoặc phê duyệt DEP-05. Giá chưa gồm chi phí dịch vụ khác. |
| SiliconFlow | API tài liệu hóa `/v1/embeddings`, ví dụ input dạng mảng và `BAAI/bge-m3` giới hạn 8192 input token [4](https://docs.siliconflow.com/cn/api-reference/embeddings/create-embeddings). | Chưa xác minh thực tế model/1024 chiều/giá/quota/vùng phục vụ qua account, hoặc tính tương thích. Privacy policy nói về xử lý/retention dữ liệu [5](https://docs.siliconflow.com/en/legals/privacy-policy); chưa đủ để kết luận zero-retention, đào tạo, xóa dữ liệu và DPA cho CV. |
| OpenRouter | Danh mục liệt kê `baai/bge-m3` giá tham khảo $0,01/triệu token và model 1024 chiều [6](https://openrouter.ai/baai/bge-m3). Là gateway nhiều provider nên cần xét cả gateway và provider đích. | Chưa xác minh hợp đồng, route đang khả dụng hoặc embedding request có enforce được policy cần thiết; docs routing nêu mặc định cho phép fallback/data collection [7](https://openrouter.ai/docs/guides/routing/provider-selection/). Batch API có retention riêng, không coi ZDR là mặc định [8](https://openrouter.ai/docs/guides/features/batch-api). Giá chỉ tham khảo, cần kiểm tra lại. |

## Preflight pilot synthetic đề xuất

1. Anh/IT chọn account và xác nhận ngân sách, quota, mạng/môi trường isolated; không chia sẻ credential trong chat, repo, log hoặc output. Lưu secret bằng cơ chế vận hành được duyệt.
2. Dùng **chỉ dữ liệu tổng hợp** được kiểm tra không chứa PII thật. Kiểm tra `/embeddings` nhận đúng `model`/`input`, thứ tự input-output, 1024 giá trị hữu hạn, lỗi/timeout, batch, max input và usage. Không bật trên worker production.
3. Pin model ID, query instruction, top-k, similarity, index version và API/provider; đối chiếu cùng corpus/label/snapshot cho lexical vs semantic. Theo dõi p50/p95 latency, requests/tokens, lỗi và fallback.
4. Synthetic chỉ đánh giá plumbing và tình huống giả lập; không xác nhận hiệu quả trên CV thật. Để dùng CV thật phải đóng phạm vi DEP-05 và chốt bộ nhãn HR/DEP-06 trước. Quyết định triển khai và E2E là riêng.

## Lưu ý về khảo sát

Tài liệu cũ `doc/BGE_LTR.md` chứa mô tả/ước lượng lịch sử và cấu hình ví dụ, không phải cam kết giá, phê duyệt provider hoặc hướng dẫn bật runtime. Kiểm tra trực tiếp thông tin hiện tại và điều khoản hợp đồng trước pilot. Chi phí dự kiến chỉ để so sánh tương đối, không phải báo giá.
