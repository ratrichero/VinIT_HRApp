# BGE, pgvector và Learning-to-Rank (LTR) cho VinIT HRApp

> **Cập nhật migration 00019:** Các hướng dẫn bật/tắt bằng biến môi trường trong tài liệu lịch sử bên dưới không áp dụng cho worker mới. Xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) về database control, giới hạn OFF và rollout/rollback không mixed-version. Code `5f5c529` đã deploy VPS test theo log người dùng; chưa chứng minh production readiness.

> Ghi chú lịch sử: tài liệu ban đầu ngày 2026-11-07. Các nhận định cũ về trạng thái môi trường và readiness không được xem là xác nhận hiện tại; xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) cho thay đổi mã mới, gate và giới hạn chưa triển khai.
> Phạm vi: semantic retrieval bằng embedding model họ BGE, lưu/truy vấn vector bằng pgvector, và Learning-to-Rank cho bước xếp hạng ứng viên.
> Nguyên tắc xuyên suốt: BGE chỉ hỗ trợ *tìm ứng viên bằng chứng*; LTR chỉ hỗ trợ *sắp xếp lại có kiểm soát*. Cả hai không thay thế deterministic rules, mandatory gate, evidence verification hoặc quyết định của HR.

## 1. Kết luận nhanh

| Hạng mục | Trạng thái code hiện tại | Trạng thái production |
|---|---|---|
| pgvector | Đã có migration `00010_pgvector_bge_ltr.sql`, bảng embedding `vector(1024)`, HNSW cosine index và registry LTR | Migration đã áp lên Supabase project hiện tại |
| BGE provider | Đã có provider `bge_http` theo OpenAI-compatible `/embeddings` | Mặc định đang tắt; chưa coi là production-ready nếu chưa cấu hình endpoint thật và đo trên golden set HR |
| Semantic retrieval | Đã tích hợp vào worker: embed CV chunks + requirement query, truy vấn pgvector/in-memory, merge với lexical chunks | Pilot cần được duyệt riêng về phạm vi, privacy, egress, môi trường và provider; chưa có benchmark HR gold |
| Nemotron-3-Embed-1B | Chưa tích hợp trực tiếp | Phù hợp để nghiên cứu/pilot, nhưng không drop-in vì native dimension 2048 và contract query/passage khác |
| LTR algorithm | Đã có pairwise logistic ranker, train offline, holdout theo group, quality gates, registry DRAFT/APPROVED/REJECTED | Chưa được bật ACTIVE |
| LTR runtime | Đã có `OFF/SHADOW/ACTIVE`, ghi `ltr_score`, chỉ reorder trong cùng mandatory status và coverage gate khi ACTIVE | Đang mặc định `OFF`; chưa có HR gold dataset và artifact APPROVED |
| HR labelling cho LTR | Đã có export weak-label từ trạng thái ứng tuyển | Chưa có UI/API thu thập HR gold label; đây là phần cần triển khai thêm nếu muốn ACTIVE nghiêm túc |

Điểm quan trọng: **LTR không cần chờ BGE**. LTR học từ đặc trưng tổng hợp của assessment hiện tại. BGE tốt hơn có thể gián tiếp làm thay đổi phân phối feature thông qua LLM fallback, nên khi đổi embedding model/index version hoặc tiêu chí matching thì LTR phải được đánh giá lại.

## 2. Kiến trúc hiện tại

```text
JD/criteria
  -> deterministic requirement_spec
  -> deterministic rule matching
  -> unresolved criteria
       -> lexical fallback chunks
       -> semantic retrieval (BGE + pgvector) bổ sung candidate chunks
       -> LLM fallback chỉ adjudicate trên candidate chunks
       -> evidence quote/page/chunk verification
  -> assessment score/status/coverage
  -> ranking policy hiện tại
       -> LTR SHADOW: chỉ ghi ltr_score
       -> LTR ACTIVE: reorder rất hẹp trong cùng gate nếu artifact đạt chuẩn
```

Các file liên quan:

- `supabase/migrations/00010_pgvector_bge_ltr.sql`
- `supabase/migrations/00011_ltr_model_governance.sql`
- `backend/app/services/embedding.py`
- `backend/app/services/semantic_retrieval.py`
- `backend/app/services/ltr.py`
- `backend/app/services/matching.py`
- `backend/app/workers/processor.py`
- `backend/scripts/export_ltr_dataset.py`
- `backend/scripts/train_ltr.py`
- `backend/scripts/register_ltr_model.py`
- `backend/tests/test_semantic_ltr.py`
- `audit/PGVECTOR_BGE_LTR_IMPLEMENTATION.md`

## 3. BGE/pgvector semantic retrieval

### 3.1. Cách hệ thống dùng BGE

BGE trong hệ thống hiện tại không chấm điểm ứng viên trực tiếp. Quy trình:

1. CV được chia chunk tối đa khoảng 900 ký tự bởi deterministic matching.
2. Worker tra cứu vector đã lưu theo `document_id + chunk_id + chunk_text_sha256 + embedding_model + index_version`; chỉ các chunk còn thiếu mới được gọi embedding provider với `kind="document"`.
3. Vector mới được chuẩn hoá L2, kiểm tra dimension, rồi lưu vào `app_private.cv_chunk_embeddings` kèm:
   - `document_id`, `chunk_id`
   - `chunk_text_sha256`
   - section/page/char offsets
   - `embedding_model`, `embedding_dimension`, `index_version`
4. Với mỗi unresolved criterion, hệ thống tạo query text từ `requirement_spec` và gọi provider với `kind="query"`.
5. Hệ thống truy vấn pgvector bằng cosine distance, lọc theo `SEMANTIC_MIN_SIMILARITY`, lấy tối đa `SEMANTIC_TOP_K`.
6. Semantic chunks được merge với lexical chunks, tối đa 5 chunk/criterion. Chunk xuất hiện ở cả lexical và semantic được ưu tiên, sau đó semantic-only, rồi lexical-only.
7. LLM fallback chỉ nhận candidate chunks này. Kết quả vẫn phải qua quote/chunk/page verification như hiện tại.

Nếu embedding provider hoặc pgvector lỗi, worker giữ lexical fallback và không làm assessment thất bại.

### 3.2. Ràng buộc an toàn của semantic retrieval

- Semantic similarity **không** tạo deterministic finding.
- Semantic similarity **không** đổi rule outcome.
- Semantic retrieval **không** được vượt qua evidence verification.
- Khi semantic bật, provider/model/dimension/index version/top-k/min-similarity/query instruction được pin vào assessment fingerprint. Đổi cấu hình semantic sẽ tạo cohort fingerprint mới, tránh trộn kết quả không tương thích.
- Bảng embedding không lưu raw CV text; chỉ lưu vector và metadata để truy vết chunk.

### 3.3. Cấu hình BGE mặc định

```dotenv
SEMANTIC_RETRIEVAL_ENABLED=false
EMBEDDING_PROVIDER=disabled
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_INDEX_VERSION=bge-index-v1
EMBEDDING_TIMEOUT_SECONDS=30
EMBEDDING_QUERY_INSTRUCTION=
SEMANTIC_TOP_K=5
SEMANTIC_MIN_SIMILARITY=0.35
```

Provider hiện tại:

- Hỗ trợ `disabled`, `hash`, `bge_http`.
- `hash` chỉ để test plumbing pgvector/retrieval; không phải BGE và không được dùng để tuyên bố chất lượng semantic.
- `bge_http` gửi `{"model": ..., "input": [...]}` tới `{EMBEDDING_API_BASE}/embeddings`, dùng Bearer token nếu có.
- Endpoint ngoài phải là HTTPS và `ALLOW_EXTERNAL_API=true`; endpoint private/loopback được phép theo policy nội bộ trong code.

### 3.4. Embedding cache và diagnostics

Từ vòng nâng cấp sau review lần 2, worker không embed lại toàn bộ CV chunks ở mỗi assessment. Cache key là document, chunk, hash nội dung, model và index version; đổi nội dung chunk, model hoặc index version sẽ tạo cache miss đúng chủ đích và chỉ embed lại phần thiếu.

Admin có thể gọi `GET /v1/admin/semantic/health` (yêu cầu role Admin) để phân biệt:

- `DISABLED`: semantic đang tắt.
- `MISCONFIGURED`: semantic bật nhưng provider/base/dimension/top-k/similarity không hợp lệ, hoặc đang dùng `hash` test provider.
- `READY_UNVERIFIED`: cấu hình hợp lệ nhưng process chưa có lượt semantic thành công.
- `OPERATIONAL`: lượt gần nhất thành công với pgvector.
- `OPERATIONAL_IN_MEMORY_PGVECTOR_UNAVAILABLE`: provider chạy được nhưng pgvector lỗi, hệ thống dùng cosine in-memory.
- `DEGRADED_FALLBACK`: lượt gần nhất lỗi provider và quay về lexical.

Diagnostics trả thêm số run, cache hit/miss, hit rate, số chunk/query đã embed, trạng thái pgvector và loại lỗi gần nhất. Endpoint không gọi provider và không trả API base/API key.

## 4. BGE-M3 có API free dùng ngay không?

Có. Lựa chọn thực dụng nhất hiện tại là **Cloudflare Workers AI** với model `@cf/baai/bge-m3`.

### 4.1. Vì sao Cloudflare phù hợp để pilot

- Có model BGE-M3 thật, output 1024 chiều, khớp trực tiếp migration `vector(1024)` hiện tại.
- Có OpenAI-compatible `/v1/embeddings`, nên khớp với provider `bge_http` mà không cần sửa code.
- Free allocation của Workers AI là 10.000 Neurons/ngày. BGE-M3 tiêu thụ 1.075 Neurons / 1 triệu input tokens, tương đương khoảng **9,3 triệu input tokens/ngày** trong hạn mức free theo bảng giá Cloudflare tại thời điểm viết tài liệu.
- Cloudflare công bố model này là Cloudflare-hosted và zero data retention. Tuy vậy, CV vẫn rời hạ tầng của VinUni khi gọi API ngoài, nên production với CV thật vẫn cần phê duyệt security/privacy.

Nguồn:

- Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare BGE-M3 model: https://developers.cloudflare.com/workers-ai/models/bge-m3/
- Cloudflare OpenAI-compatible endpoints: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/

### 4.2. Cấu hình Cloudflare cho repo hiện tại

Tạo Cloudflare API Token có quyền Workers AI, lấy Account ID, rồi đặt:

```dotenv
SEMANTIC_RETRIEVAL_ENABLED=true
ALLOW_EXTERNAL_API=true

EMBEDDING_PROVIDER=bge_http
EMBEDDING_API_BASE=https://api.cloudflare.com/client/v4/accounts/<CLOUDFLARE_ACCOUNT_ID>/ai/v1
EMBEDDING_API_KEY=<CLOUDFLARE_API_TOKEN>
EMBEDDING_MODEL=@cf/baai/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_INDEX_VERSION=bge-m3-cloudflare-v1
EMBEDDING_QUERY_INSTRUCTION=
SEMANTIC_TOP_K=5
SEMANTIC_MIN_SIMILARITY=0.35
```

Test endpoint trước khi bật worker:

```bash
curl "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/ai/v1/embeddings" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "@cf/baai/bge-m3",
    "input": ["Python developer with 3 years of FastAPI experience"]
  }'
```

Điều kiện pass:

- HTTP 200.
- Có `data[0].embedding`.
- Độ dài vector đúng 1024.
- Không dùng nhầm model name `BAAI/bge-m3` cho Cloudflare; Cloudflare dùng `@cf/baai/bge-m3`.

### 4.3. Giới hạn của phương án free

- Phù hợp dev/staging/pilot và hiệu chuẩn ngưỡng similarity.
- Hạn mức free reset theo ngày; vượt hạn mức trên Workers Free có thể làm request lỗi cho tới ngày hôm sau hoặc phải nâng cấp.
- Độ trễ và quota phụ thuộc Cloudflare; embedding lỗi không làm assessment fail, nhưng semantic benefit sẽ mất và hệ thống quay về lexical.
- Không nên gửi CV thật ra API ngoài khi chưa có phê duyệt bảo mật, điều khoản lưu trữ/xoá dữ liệu và đánh giá nhà cung cấp.
- Khi chuyển sang self-host, giữ nguyên model/dimension và đổi `EMBEDDING_API_BASE`; nên bump `EMBEDDING_INDEX_VERSION` nếu serving stack cho vector khác đáng kể.

### 4.4. Các lựa chọn API khác

| Lựa chọn | Đánh giá |
|---|---|
| Self-host BGE-M3 bằng TEI/vLLM/Xinference | Khuyến nghị cho production nếu có GPU/VPS phù hợp; kiểm soát dữ liệu tốt nhất |
| Cloudflare Workers AI | Dùng ngay, có free allocation, hợp pilot |
| SiliconFlow | Có API BGE-M3 nhưng chủ yếu credit dùng thử; không nên coi là free lâu dài |
| Hugging Face Inference Providers | Không còn là free tier bền vững cho tài khoản Free; cần credits/gói trả phí |
| OpenRouter/Together/DeepInfra và các aggregator | Thường tính phí theo token; BGE-M3 rẻ nhưng không phải free |

## 5. Đánh giá Nemotron-3-Embed-1B

### 5.1. Điểm mạnh

`nvidia/Nemotron-3-Embed-1B-BF16` / NIM `nvidia/nemotron-3-embed-1b` là embedding model mới của NVIDIA, khoảng 1,14B tham số, hỗ trợ retrieval đa ngôn ngữ gồm tiếng Việt, context dài và use case RAG/search. Model phù hợp về mặt bài toán với CV/JD song ngữ Anh-Việt.

Nguồn:

- Hugging Face model card: https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16
- NVIDIA NIM API: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-embed-1b
- NVIDIA OpenAI-compatible NIM docs: https://docs.nvidia.com/nim/nemo-retriever/text-embedding/latest/use-the-api-openai.html

### 5.2. Vì sao chưa drop-in với hệ thống hiện tại

| Vấn đề | Hiện trạng VinIT HRApp | Tác động |
|---|---|---|
| Native dimension 2048 | Migration cố định `vector(1024)` | Không lưu trực tiếp được |
| pgvector HNSW với `vector` | Giới hạn index khoảng 2000 dimensions | Vector 2048 không dùng HNSW `vector` hiện tại |
| NIM không hỗ trợ giảm dimension qua request | Provider hiện validate đúng dimension cấu hình | Cần slice ở backend/serving rồi normalize lại |
| Query/passage contract | Provider chưa gửi `input_type`, chưa prefix document | Cần bổ sung contract cho Nemotron |
| Hạ tầng | Backend hiện không có GPU serving stack riêng | Cần NIM/vLLM + GPU NVIDIA nếu self-host |

Model card Nemotron cho phép slice vector, ví dụ lấy 1024 chiều đầu từ vector 2048 và L2-renormalize trước khi tính similarity. Nếu dùng hướng này, có thể giữ nguyên schema pgvector hiện tại.

### 5.3. Phương án tích hợp Nemotron nếu muốn pilot

Phương án ít thay đổi nhất:

1. Serve Nemotron bằng NIM hoặc vLLM trên GPU nội bộ.
2. Mở rộng provider để hỗ trợ một trong hai contract:
   - NIM: gửi `input_type="query"` hoặc `input_type="passage"`.
   - vLLM/HF-style: prefix `query:` cho query và `passage:` cho document nếu serving không tự áp dụng.
3. Nhận vector native 2048, slice xuống 1024 và L2-renormalize trước khi lưu pgvector.
4. Cấu hình storage dimension vẫn là 1024 và đặt index version riêng, ví dụ `nemotron-3-embed-1b-s1024-v1`.
5. Chạy A/B với BGE-M3 trên HR golden set trước khi quyết định.

Phương án native 2048 không được khuyến nghị cho vòng đầu vì phải thay đổi thiết kế lưu trữ/index, ví dụ `halfvec(2048)`, exact search ở quy mô nhỏ, hoặc vector database khác.

### 5.4. Khuyến nghị model

- Muốn bật nhanh, ít rủi ro tích hợp: **BGE-M3**.
- Có GPU NVIDIA và muốn thử chất lượng retrieval mới: pilot **Nemotron-3-Embed-1B** theo phương án slice 1024.
- Không chọn model chỉ bằng benchmark công bố; phải đo trên CV/JD thật của VinUni bằng golden set HR.

## 6. Điều kiện để bật BGE thật

Trước khi bật `SEMANTIC_RETRIEVAL_ENABLED=true` cho dữ liệu thật:

1. **Endpoint sẵn sàng**
   - Cloudflare Workers AI, TEI, vLLM, Xinference hoặc endpoint tương thích.
   - Backend/worker gọi được endpoint.
   - Dimension trả về đúng 1024 hoặc đã có cơ chế slice/normalize được kiểm chứng.
2. **Hiệu chuẩn trên golden set HR**
   - Có tập CV/JD/criterion được HR xác nhận chunk nào chứa bằng chứng.
   - Đo candidate Recall@5, unresolved rate, false MATCH, false NO_MATCH/UNCLEAR, latency và lỗi provider.
   - Tinh chỉnh `SEMANTIC_MIN_SIMILARITY` và `SEMANTIC_TOP_K`; không mặc định tin `0.35` cho mọi model/serving stack.
3. **Bảo mật và riêng tư**
   - Nếu dùng API ngoài: phê duyệt egress, điều khoản retention, khu vực xử lý dữ liệu và quản lý API token.
   - Nếu dùng CV thật: ưu tiên self-host hoặc nhà cung cấp đã được phê duyệt.
4. **Vận hành**
   - Bật trước ở staging/pilot.
   - Theo dõi log `Semantic embedding unavailable`, `pgvector persistence unavailable`, `pgvector query unavailable`.
   - Rollback bằng cách đặt `SEMANTIC_RETRIEVAL_ENABLED=false` và restart worker/backend liên quan.

## 7. LTR là gì trong hệ thống này?

LTR là mô hình học cách sắp xếp ứng viên dựa trên dữ liệu lịch sử đã gán nhãn. Trong VinIT HRApp, LTR **không** quyết định ứng viên đạt hay không đạt. Nó chỉ học một `ltr_score` phụ trợ từ các đặc trưng tổng hợp của assessment.

Luồng đúng:

```text
Deterministic matching + evidence verification
  -> matching_status / matching_score / evidence_coverage
  -> ranking policy hiện tại là nguồn quyết định chính
  -> LTR SHADOW: ghi điểm để so sánh
  -> LTR ACTIVE: chỉ đổi thứ tự trong cùng mandatory status + coverage gate
```

LTR không được:

- Cho ứng viên `POSSIBLE_MISMATCH` vượt ứng viên `MEETS_MANDATORY`.
- Cho ứng viên thiếu coverage vượt coverage eligibility gate.
- Thay đổi `matching_status`, `matching_score` gốc hoặc kết quả criterion.
- Dùng dữ liệu định danh/nhạy cảm như tên, email, giới tính, tuổi, trường học để xếp hạng.

## 8. LTR đã được triển khai đến đâu?

### 8.1. Phần thuật toán đã có

`backend/app/services/ltr.py` đã có:

- Bộ 13 feature cố định.
- Pairwise logistic ranker học trọng số tuyến tính.
- Chuẩn hoá feature bằng mean/std của tập train.
- Tách holdout theo group/position, không tách random theo từng dòng để tránh leakage cùng position.
- Metrics: NDCG@10, pairwise accuracy, số group được đánh giá.
- Artifact JSON gồm feature names, means, stds, weights, training metadata, train/test metrics và `model_version` suy ra từ hash dữ liệu.
- Fail-closed khi thiếu examples, thiếu group hoặc chỉ có một mức label.

### 8.2. Feature hiện tại

| Feature | Ý nghĩa |
|---|---|
| `matching_score` | Điểm trên các tiêu chí đã có bằng chứng, chuẩn hoá 0-1 theo `matching-v2.1` |
| `evidence_coverage` | Độ bao phủ bằng chứng |
| `strong_match_rate` | Tỷ lệ criterion STRONG_MATCH |
| `match_rate` | Tỷ lệ criterion MATCH |
| `no_match_rate` | Tỷ lệ criterion NO_MATCH |
| `unclear_rate` | Tỷ lệ criterion UNCLEAR |
| `rule_decision_rate` | Tỷ lệ quyết định bởi rule |
| `llm_decision_rate` | Tỷ lệ quyết định bởi LLM fallback |
| `avg_evidence_strength` | Độ mạnh bằng chứng trung bình |
| `mandatory_no_match` | Có mandatory criterion bị NO_MATCH hay không |
| `needs_verification` | Trạng thái NEEDS_HR_VERIFICATION |
| `meets_mandatory` | Trạng thái MEETS_MANDATORY |
| `possible_mismatch` | Trạng thái POSSIBLE_MISMATCH |

Không có feature định danh hoặc demographic trong schema hiện tại.

### 8.3. Registry và runtime đã có

Migration `00010` đã tạo nền registry; migration `00011` bổ sung governance:

- `app_private.ltr_model_versions`: registry artifact, metrics, feature names, training counts, data hash, trạng thái `DRAFT/APPROVED/REJECTED`, artifact hash và thông tin reviewer/lý do.
- `app_private.ltr_model_review_events`: lịch sử REGISTERED/APPROVED/REJECTED có actor, artifact hash, metrics snapshot và reason.
- `app_private.ranking_runs.ltr_model_version`, `app_private.ranking_runs.ltr_mode`.
- `app_private.ranking_items.ltr_score`.

Worker `_load_ltr_model` hoạt động như sau:

- `LTR_MODE=OFF`: không load model.
- `SHADOW`: load model để ghi điểm nhưng không đổi thứ tự.
- `ACTIVE`: chỉ load artifact registry có `status=APPROVED`; artifact `REJECTED` bị chặn ở mọi mode.
- Nếu dùng `LTR_MODEL_PATH`, artifact file vẫn phải qua quality gates ở môi trường non-production. Từ vòng nâng cấp sau review lần 2, `ACTIVE` với `APP_ENV=production` bị chặn nếu nạp bằng file; production ACTIVE chỉ dùng artifact registry đã `APPROVED`.
- Nếu artifact không đạt gate, worker bỏ qua LTR và giữ nguyên ranking hiện tại.

Quality gates mặc định trong cấu hình:

```dotenv
LTR_MODE=OFF
LTR_MODEL_PATH=
LTR_MODEL_VERSION=
LTR_MIN_NDCG_AT_10=0.70
LTR_MIN_PAIRWISE_ACCURACY=0.65
LTR_MIN_HOLDOUT_EXAMPLES=20
LTR_MIN_HOLDOUT_GROUPS=2
```

### 8.4. Hành vi ranking theo mode

`rank_applications` trong `backend/app/services/matching.py`:

- `OFF`: status mandatory -> matching score -> evidence coverage -> application_id.
- `SHADOW`: thứ tự giống `OFF`, nhưng mỗi item có thêm `ltr_score`.
- `ACTIVE`: status mandatory -> coverage eligibility -> `ltr_score` giảm dần -> matching score -> evidence coverage -> application_id.

Rank number vẫn chỉ cấp cho ứng viên có coverage đạt `MIN_EVIDENCE_COVERAGE` và không ở trạng thái `NOT_ASSESSED`.

## 9. LTR cần triển khai như thế nào để dùng thật?

Không cần viết lại thuật toán. Phần còn lại là **dữ liệu nhãn, quy trình phê duyệt, shadow evaluation và giám sát**. Lộ trình khuyến nghị:

### Bước 0: Đóng băng baseline

Trước khi thu nhãn hoặc train:

- Giữ `LTR_MODE=OFF`.
- Ghi lại versions: assessment policy, matching policy, ranking policy, criteria prompt, deterministic rules, semantic config nếu có.
- Không train LTR trên dữ liệu trộn nhiều policy version mà không ghi metadata.
- Nếu BGE semantic đang bật, ghi rõ embedding provider/model/index version vì thay đổi semantic có thể làm thay đổi feature distribution.

### Bước 1: Tạo dataset có nhãn

Mỗi example cần:

```json
{
  "group_id": "<position_id hoặc position_id:criteria_version_id>",
  "position_id": "<position_id>",
  "application_id": "<application_id>",
  "assessment_id": "<assessment_id>",
  "label": 3,
  "label_source": "HR_GOLD",
  "features": {
    "matching_score": 0.86,
    "evidence_coverage": 0.92
  }
}
```

Trong train code, `features` sẽ được map theo đúng 13 feature cố định; feature thiếu được coi là 0.0. Dataset production nên export đủ 13 feature từ `extract_ranking_features` thay vì nhập tay.

#### 9.1.1. Weak label hiện có

Script hiện tại:

```bash
cd backend
python scripts/export_ltr_dataset.py --output ../data/ltr_weak_labels.json
```

Script này:

- Lấy assessment COMPLETED mới nhất của mỗi application.
- Group theo position.
- Map trạng thái ứng tuyển thành nhãn yếu:
  - `ACCEPTED/HIRED` -> 3
  - `OFFERED/INTERVIEW/SHORTLIST` -> 2
  - `IN_REVIEW/NEW` -> 1
  - `REJECTED*/WITHDRAWN` -> 0
- Đánh dấu `label_source=WEAK`.

Weak label chỉ dùng để thử pipeline hoặc SHADOW thử nghiệm. Nó phản ánh workflow lịch sử, có thể chứa thiên lệch vận hành, thiếu hụt dữ liệu và quyết định không nhất quán. **Không dùng weak label để phê duyệt ACTIVE.**

#### 9.1.2. HR gold label cần có

HR cần gán relevance theo rubric thống nhất, ví dụ:

| Label | Ý nghĩa gợi ý |
|---:|---|
| 3 | Rất phù hợp: đáp ứng mandatory quan trọng, bằng chứng mạnh, nên ưu tiên phỏng vấn |
| 2 | Phù hợp: đáp ứng phần lớn yêu cầu, có thể phỏng vấn |
| 1 | Biên/chưa rõ: thiếu bằng chứng hoặc cần xác minh thêm |
| 0 | Không phù hợp cho position này |

Yêu cầu chất lượng nhãn:

- HR chấm dựa trên CV/JD/criteria, không nhìn `matching_score`, rank hiện tại hoặc `ltr_score` để tránh leakage và self-fulfilling label.
- Mỗi position là một group; ứng viên chỉ so sánh trong cùng position/criteria version.
- Nên có tối thiểu hai mức label khác nhau; tốt nhất đủ cả 0-3.
- Một phần dataset nên được hai HR chấm độc lập để đo agreement; bất đồng cần adjudication.
- Lưu reviewer, thời gian chấm, rubric version, criteria version và assessment snapshot dùng để trích feature.
- Không dùng dữ liệu định danh/nhạy cảm trong feature; label cũng không được dựa trên đặc điểm cá nhân không liên quan đến yêu cầu công việc.

#### 9.1.3. Quy mô dữ liệu

Code train function có thể chạy từ 30 examples/5 groups cho test, nhưng CLI production mặc định fail-closed ở:

- Tối thiểu 200 examples.
- Tối thiểu 10 groups/positions.

Khuyến nghị production thực tế:

- Tối thiểu đạt CLI gate 200 examples / 10 groups chỉ để bắt đầu SHADOW.
- Mục tiêu tốt hơn: 1.000+ examples, 30+ positions, nhiều phòng ban/loại vị trí, phân bố label không quá lệch.
- Holdout phải là các position hoàn toàn không xuất hiện ở train. Code hiện tách khoảng 20% group theo hash deterministic.
- Nên bổ sung đánh giá theo thời gian: train trên các đợt tuyển cũ, test trên đợt tuyển mới hơn.

#### 9.1.4. Phần code còn thiếu cho labelling production

Hiện repo chưa có UI/API quản lý HR gold label. Có hai cách triển khai:

**Cách A - MVP thủ công có kiểm soát**

1. Dùng `export_ltr_dataset.py` để lấy feature snapshot và application IDs.
2. HR chấm trên file/CRM riêng theo rubric, chỉ trả về `application_id`, `group_id`, `label`, reviewer và rubric version.
3. Script/operator merge label HR vào dataset, đổi `label_source` thành `HR_GOLD`.
4. Lưu dataset đã gán nhãn ở nơi có kiểm soát truy cập; dataset export hiện chỉ chứa IDs/features/outcomes, không chứa CV text.

Cách này đủ để pilot nhưng dễ sai phiên bản và khó audit nếu làm lâu dài.

**Cách B - Production labelling workflow (khuyến nghị nếu ACTIVE)**

Cần triển khai thêm:

- Bảng lưu nhãn HR, ví dụ `app_private.ltr_training_labels` với các cột: position/criteria version, application, assessment, label 0-3, reviewer, reviewed_at, rubric_version, label_source, adjudication status.
- API/UI cho HR xem CV/JD/criteria theo position, chấm label mà không hiển thị điểm/rank của hệ thống.
- Cơ chế gán việc, double-labelling một phần, adjudication khi hai HR lệch nhau.
- Export HR gold dataset join label với feature snapshot của đúng assessment.
- Audit log cho label và approval.

### Bước 2: Train offline và kiểm tra gates

Sau khi có HR gold dataset:

```bash
cd backend
python scripts/train_ltr.py ../data/ltr_hr_gold.json \
  --output ../models/ltr-artifact.json \
  --report ../models/ltr-report.json \
  --check
```

Mặc định script yêu cầu:

- `--min-examples 200`
- `--min-groups 10`
- `--min-ndcg 0.70`
- `--min-pairwise 0.65`
- `--min-holdout-examples 20`
- `--min-holdout-groups 2`

`--check` trả exit code 2 nếu holdout metrics không đạt gate. Không được hạ gate chỉ để có artifact bằng mọi giá; nếu không đạt, cần xem lại nhãn, feature, phân phối position và rubric.

Báo cáo train cần lưu:

- `model_version`
- Số examples/groups/train/test
- Số train pairs
- Train/test NDCG@10 và pairwise accuracy
- Gate pass/fail
- Dataset hash

### Bước 3: Đăng ký artifact vào registry

```bash
cd backend
python scripts/register_ltr_model.py ../models/ltr-artifact.json
```

Script chỉ đăng ký artifact ở trạng thái `DRAFT`, đồng thời lưu `artifact_sha256` và sự kiện `REGISTERED`. Nếu cùng `model_version` đã tồn tại với artifact khác, script từ chối ghi đè. Nó không approve và không activate model.

Từ migration `00011_ltr_model_governance`, phê duyệt phải qua Admin API để lưu actor, lý do, artifact hash, metrics snapshot và audit event:

```bash
curl -X POST "$API_BASE/v1/admin/ltr/models/<model_version>/approve" \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Đạt NDCG/pairwise holdout gates và đã review dataset"}'
```

Từ chối dùng endpoint tương tự `/reject` với lý do bắt buộc. API chỉ cho phép chuyển từ `DRAFT`; approve còn kiểm tra quality gates và artifact hash. Không sửa trực tiếp `status` bằng SQL trong vận hành bình thường.

Yêu cầu phê duyệt:

- Người train và người approve nên khác nhau nếu có thể.
- Lý do phê duyệt phải đối chiếu được với báo cáo holdout, dataset hash và phạm vi position áp dụng.
- Nếu artifact không đạt yêu cầu, reject thay vì để DRAFT mơ hồ.
- Trong mã mới, Admin UI cũng có bề mặt review model và chọn managed SHADOW/OFF; xem `AI_ADMIN_ROUTING_STATUS.md`. Code chưa được triển khai và chọn cấu hình không thay thế quyết định pilot.

### Bước 4: Chạy SHADOW

Cấu hình staging/production shadow:

```dotenv
LTR_MODE=SHADOW
LTR_MODEL_VERSION=<model_version>
LTR_MODEL_PATH=
LTR_MIN_NDCG_AT_10=0.70
LTR_MIN_PAIRWISE_ACCURACY=0.65
LTR_MIN_HOLDOUT_EXAMPLES=20
LTR_MIN_HOLDOUT_GROUPS=2
```

Mục tiêu SHADOW:

- Xác nhận worker load đúng artifact.
- Xác nhận `ranking_runs.ltr_mode=SHADOW`, `ltr_model_version` đúng và `ranking_items.ltr_score` được ghi.
- So sánh thứ tự deterministic hiện tại với thứ tự nếu ACTIVE.
- Không đổi trải nghiệm HR trong giai đoạn này.

Chỉ số cần báo cáo trong SHADOW:

- NDCG@10 và pairwise accuracy trên nhãn HR holdout mới.
- Top-5/Top-10 overlap giữa ranking hiện tại và LTR.
- Kendall tau-b hoặc rank correlation theo position.
- Tỷ lệ ứng viên thay đổi rank, mức thay đổi trung bình/lớn nhất.
- Kiểm tra tuyệt đối: 0 trường hợp LTR làm ứng viên vượt mandatory status hoặc coverage gate.
- Phân tích theo department/position family, ngôn ngữ CV, nguồn ứng viên và các nhóm hợp lệ khác để phát hiện sai lệch bất thường.
- Tỷ lệ lỗi load model/gate fail trong log.

Hiện code đã ghi đủ dữ liệu để phân tích cơ bản, nhưng chưa có script/dashboard báo cáo SHADOW riêng. Đây là phần nên bổ sung trước ACTIVE.

### Bước 5: Kích hoạt ACTIVE có giới hạn

Chỉ bật ACTIVE khi đồng thời thỏa:

- Dataset là HR gold label, không phải weak label.
- Train CLI đạt gates với `--check`.
- Artifact đã đăng ký và được `APPROVED`.
- SHADOW chạy ổn qua ít nhất một chu kỳ tuyển dụng đại diện hoặc số ranking runs đủ lớn theo quyết định HR/ops.
- Không có vi phạm mandatory/coverage gate.
- Có kế hoạch rollback và người chịu trách nhiệm phê duyệt.

Cấu hình:

```dotenv
LTR_MODE=ACTIVE
LTR_MODEL_VERSION=<approved_model_version>
LTR_MODEL_PATH=
```

Rollout nên bắt đầu ở một nhóm position giới hạn nếu vận hành cho phép tách cấu hình worker; nếu không, bật toàn cục nhưng theo dõi sát trong các ranking runs đầu tiên.

Rollback:

```dotenv
LTR_MODE=OFF
```

Sau đó restart worker và chạy lại ranking nếu cần công bố lại thứ tự. Các ranking runs cũ vẫn giữ `ltr_mode`/model version để truy vết, không sửa lịch sử.

### Bước 6: Giám sát và retrain

Sau ACTIVE cần theo dõi:

- Drift của feature distribution theo thời gian.
- Tỷ lệ UNCLEAR/LLM fallback thay đổi sau khi đổi prompt/model/BGE.
- Hiệu quả theo position mới: LTR train trên position cũ có thể không tổng quát cho họ vị trí mới.
- Feedback loop: HR nhìn ranking ACTIVE rồi quyết định, sau đó outcome được dùng làm label mới có thể củng cố chính ranking cũ. Cần giữ một phần nhãn blind/independent để đánh giá.
- Retrain khi đổi criteria policy, matching policy, prompt, embedding model/index version, rubric hoặc khi có đủ nhãn HR mới.
- Mỗi lần retrain tạo artifact/version mới; không ghi đè artifact đang chạy.

## 10. Những phần cần triển khai thêm trước LTR ACTIVE production

| Hạng mục | Mức cần thiết | Ghi chú |
|---|---|---|
| HR gold dataset | Bắt buộc | Không có dataset này thì LTR chỉ dừng ở thử nghiệm |
| Rubric chấm nhãn + adjudication | Bắt buộc | Giảm nhiễu nhãn và leakage |
| Quy trình approve artifact | Đã có nền tảng trong mã | API + UI review và managed SHADOW/OFF có actor/reason/hash/audit; chưa triển khai hay kiểm thử staging |
| SHADOW evaluation report | Bắt buộc trước ACTIVE | So sánh ranking hiện tại vs LTR theo position/gate |
| Monitoring sau ACTIVE | Bắt buộc | Drift, gate violations, model load failures |
| HR labelling UI/API | Khuyến nghị mạnh | Cần nếu làm LTR lâu dài thay vì file thủ công |
| Fairness/bias slices | Khuyến nghị mạnh | Chỉ dùng thuộc tính hợp lệ, phục vụ audit; không đưa demographic vào feature |
| Temporal holdout | Khuyến nghị | Test trên đợt tuyển mới hơn train để đo tổng quát hoá |
| Group theo `position_id:criteria_version_id` | Khuyến nghị | Tránh trộn các phiên bản JD/criteria khác nhau trong cùng group |

## 11. Lộ trình triển khai tổng hợp khuyến nghị

1. **Giữ nguyên baseline deterministic** và `LTR_MODE=OFF`.
2. **Pilot BGE-M3** bằng Cloudflare Workers AI ở staging hoặc endpoint self-host; đo trên golden set semantic retrieval.
3. **Đóng băng cấu hình** matching/semantic trước khi thu HR label cho LTR.
4. **Xây HR gold dataset**: bắt đầu MVP bằng export + HR labelling có kiểm soát; nếu làm production lâu dài, xây labelling workflow.
5. **Train offline** bằng `train_ltr.py --check`; không đạt gate thì không đăng ký APPROVED.
6. **Register DRAFT**, review báo cáo, approve có truy vết.
7. **Chạy SHADOW**, tạo báo cáo so sánh và kiểm tra gate violations.
8. **ACTIVE giới hạn**, theo dõi ranking runs đầu tiên, sẵn sàng rollback về `OFF`.
9. **Retrain định kỳ** khi có nhãn mới hoặc policy/model thay đổi.

## 12. Checklist quyết định go/no-go

### BGE

- [ ] Endpoint thật trả vector 1024 ổn định.
- [ ] Đã đo Recall@5/false outcomes trên golden set HR.
- [ ] Đã chốt `SEMANTIC_MIN_SIMILARITY`, `SEMANTIC_TOP_K`, `EMBEDDING_INDEX_VERSION`.
- [ ] Đã phê duyệt privacy/security nếu gọi API ngoài.
- [ ] Có rollback bằng `SEMANTIC_RETRIEVAL_ENABLED=false`.

### LTR

- [ ] Có HR gold dataset, không chỉ weak label.
- [ ] Dataset đạt tối thiểu CLI: 200 examples, 10 groups.
- [ ] Holdout đạt NDCG@10 >= 0.70 và pairwise accuracy >= 0.65.
- [ ] Artifact đăng ký DRAFT và được APPROVED rõ ràng.
- [ ] SHADOW không có gate violation và báo cáo được HR/ops chấp nhận.
- [ ] Có monitoring, rollback `LTR_MODE=OFF`, và quy trình retrain.

## 13. Tài liệu liên quan

- `doc/MATCHING_STABILITY.md`
- `audit/PGVECTOR_BGE_LTR_IMPLEMENTATION.md`
- `audit/MATCHING_PHASE0_2_AUDIT.md`
- `audit/MATCHING_PHASE0_2_FIXES.md`
- `supabase/migrations/00010_pgvector_bge_ltr.sql`
