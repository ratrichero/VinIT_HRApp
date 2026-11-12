# Ổn định matching CV–JD

> **Cập nhật migration 00019:** Các hướng dẫn bật/tắt bằng biến môi trường trong tài liệu lịch sử bên dưới không áp dụng cho worker mới. Xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) về database control, giới hạn OFF và rollout/rollback không mixed-version. Chưa triển khai thay đổi này lên môi trường thật.

Tài liệu này mô tả kiến trúc matching Phase 0–2 cùng lớp semantic retrieval (pgvector/BGE) và Learning-to-Rank được triển khai theo hướng tắt mặc định, có gate an toàn. Tài liệu liên quan: [thiết kế database](HRA_DatabaseDesign.md), [kiến trúc LLM](HRA_LLM_Architecture.md), [kiến trúc giải pháp](HRA_ArchitectureDesign.md), [vận hành/triển khai](../DEPLOYMENT.md) và [báo cáo triển khai pgvector/BGE/LTR](../audit/PGVECTOR_BGE_LTR_IMPLEMENTATION.md).

## 1. Nguyên tắc

1. **LLM không cho điểm cuối.** Điểm, gate bắt buộc, độ phủ bằng chứng và thứ hạng do code xác định tính từ findings đã kiểm chứng.
2. **Không có bằng chứng không đồng nghĩa không đáp ứng.** Thiếu bằng chứng luôn là `UNCLEAR`/cần HR xác minh, trừ khi CV có dữ kiện đo được mâu thuẫn rõ ràng (ví dụ số năm hoặc điểm IELTS thấp hơn yêu cầu).
3. **Cùng đầu vào phải cho cùng đầu ra.** Assessment được đóng băng bằng fingerprint; chạy lại cùng fingerprint phải tái sử dụng kết quả đã lưu thay vì gọi LLM lần nữa.
4. **Mọi thay đổi hành vi đều phải tăng version.** Không âm thầm thay rule, prompt, scoring hoặc model rồi trộn với kết quả cũ.

## 2. Luồng xử lý hiện tại

```text
CV đã redaction
  -> profile facts + CV text hash
  -> assessment fingerprint
       -> đã có COMPLETED cùng fingerprint: tái sử dụng, không gọi LLM
       -> chưa có: chunk CV theo page/section/paragraph/sentence
                    -> requirement spec từ rubric đã duyệt
                    -> deterministic rule engine
                    -> LLM fallback chỉ cho tiêu chí chưa quyết định,
                       chỉ với candidate chunks của từng tiêu chí
                    -> hợp nhất findings theo đúng rubric
                    -> verify quote bằng normalized span + page/offset
                    -> score / must-have gate / evidence coverage
                    -> ranking mặc định: status -> score -> coverage -> application_id
                       (LTR ACTIVE, nếu đạt gate, chỉ reorder trong cùng status/coverage gate)
```

### 2.1 Fingerprint

Fingerprint là SHA-256 của:

- định danh application/position;
- JD version, criteria version và toàn bộ rubric đã duyệt;
- profile version và canonical profile facts;
- SHA-256 của CV text sau redaction;
- snapshot runtime AI công khai (không chứa API key/ciphertext);
- `LLM_SEED` nếu được cấu hình;
- matching prompt version, matching policy version và deterministic rules version;
- ranking policy version, ngày đánh giá dùng cho khoảng ngày kết thúc ở hiện tại;
- trực tiếp các tham số điểm/coverage đang hiệu lực: score map, `MIN_EVIDENCE_COVERAGE`, `MIN_EVIDENCE_STRENGTH`, trọng số hai nhóm và cờ strict JSON Schema. Thay các giá trị này qua môi trường vẫn đổi fingerprint dù quên tăng version string.

Nếu một `COMPLETED` assessment có cùng fingerprint tồn tại, worker bỏ qua application đó. Khi semantic **tắt**, operation mới vẫn có thể tái sử dụng assessment có fingerprint giống hệt. Khi semantic **bật**, fingerprint bổ sung ID operation: operation khác phải đánh giá lại để không tái sử dụng kết quả của route BGE/lexical có khả dụng khác; cache vector theo route vẫn được tái sử dụng. Recovery cùng operation tái sử dụng assessment đã hoàn thành nếu fingerprint và môi trường hiệu lực không thay đổi; thay gate/cấu hình môi trường có thể tạo fingerprint mới. Đổi chính sách này làm tăng số lần gọi LLM/chi phí; cần đo drift và chi phí trước pilot. Không sửa trực tiếp kết quả đã lưu.

### 2.2 Chunk và requirement spec

CV được chia thành chunk có:

- `chunk_id` ổn định theo thứ tự văn bản;
- page number nếu có marker `--- Page N ---`;
- `char_start`/`char_end` trỏ đúng vào CV text;
- section suy ra từ heading: `WORK`, `PROJECT`, `SKILL`, `EDUCATION`, `CERTIFICATION`, `LANGUAGE`, `SUMMARY` hoặc `OTHER`.

Requirement spec có dạng cấu trúc (`kind`, `terms`, `min_years`, cấp bằng, ngôn ngữ và ngưỡng IELTS/TOEIC/CEFR) và được lưu trên từng criterion. AI/HR có thể sửa spec trong bản nháp; khi HR duyệt, các spec suy luận còn thiếu được materialize vào rubric để HM duyệt đúng spec sẽ dùng khi đánh giá. Spec đã lưu là nguồn sự thật; engine chỉ suy luận bản nháp khi criterion chưa có spec.

### 2.3 Rule engine

| Loại | Quyết định xác định khi | Không quyết định khi |
|---|---|---|
| Kỹ năng | term/alias xuất hiện trong chunk liên quan với coverage đủ mạnh | chỉ xuất hiện yếu/ngoài ngữ cảnh hoặc không thấy |
| Số năm | tổng duration riêng biệt đủ, profile total, hoặc khoảng ngày đã merge đủ/không đủ | tổng duration rời rạc dưới ngưỡng nhưng chưa đáng tin cậy để kết luận thiếu |
| Bằng cấp | quote trong CV parse được cấp bằng đạt; hoặc section Education đầy đủ cho thấy cấp cao nhất thấp hơn yêu cầu | profile fact cao hơn quote CV, hoặc bằng thấp chỉ xuất hiện ngoài Education |
| Chứng chỉ | term chứng chỉ xuất hiện trong chunk liên quan | không thấy chứng chỉ |
| Ngoại ngữ | một mức nhất quán đạt hoặc thấp hơn yêu cầu, quote chứa nguyên mức đó | nhiều mức mâu thuẫn cho cùng bài test, hoặc CV chỉ nêu tên ngôn ngữ |

Rule finding có `decision_source=RULE`, `evidence_strength`, `evidence_chunk_id` và `rule_version`. Token cấu thành của một phrase (ví dụ `programming`) không tự thỏa mãn concept (`Python programming`). Quote lưu xuống evidence là exact substring lấy từ CV text; worker vẫn verify lại span/page trước khi chấm và ưu tiên occurrence thuộc chunk/page được gợi ý khi quote lặp lại.

`HYBRID` hiện là giá trị dành cho quyết định hợp nhất trong tương lai; đường code hiện tại gán từng criterion là `RULE` hoặc `LLM`, không mô tả một finding LLM thường là hybrid.

### 2.4 LLM fallback

LLM chỉ nhận các tiêu chí mà rule chưa quyết định, rubric con tương ứng và tối đa 5 candidate chunks cho từng criterion. Model phải trích quote từ các chunk đó và trả `evidence.chunk_id`; toàn bộ CV không được gửi trong fallback path. Từng finding được validate độc lập: finding lỗi enum/schema chỉ thành `UNCLEAR` cho criterion đó, không làm fail application. `LLM_STRICT_JSON_SCHEMA=true` mới yêu cầu provider enforce JSON Schema; mặc định vẫn dùng `json_object` và Pydantic validation phía client vì một số endpoint compatible không hỗ trợ strict schema. Quote không tìm được span trong CV sẽ bị hạ `UNCLEAR`.

`temperature=0` và seed tùy chọn chỉ giúp nhà cung cấp ổn định hơn theo cơ chế best-effort; chúng **không** thay thế fingerprint/rule engine.

### 2.5 Công thức điểm và độ phủ từ `matching-v2.1`

Từ `MATCHING_POLICY_VERSION=matching-v2.1`, ba chỉ số có ý nghĩa tách bạch:

- `matching_score`: trung bình có trọng số **chỉ trên các tiêu chí đã đủ bằng chứng để tính điểm**. `UNCLEAR` bị loại khỏi cả tử số và mẫu số, không bị tính như 0. Nếu chưa có tiêu chí nào tính được điểm, score là `null`.
- `evidence_coverage`: trọng số đã tính được điểm chia cho tổng trọng số tiêu chí áp dụng. Đây là chỉ số cho biết mức độ đầy đủ của bằng chứng.
- `matching_status`: gate bắt buộc và nhu cầu HR xác minh. Coverage dưới ngưỡng hoặc mandatory `UNCLEAR` vẫn đưa hồ sơ sang `NEEDS_HR_VERIFICATION`; mandatory `NO_MATCH` đã có bằng chứng vẫn có thể tạo `POSSIBLE_MISMATCH`.

Ví dụ hai tiêu chí có trọng số hiệu dụng 50/50, một `STRONG_MATCH` và một `UNCLEAR`: `matching_score=100`, `evidence_coverage=0.5`, hồ sơ vẫn cần HR xác minh vì coverage dưới ngưỡng. Giao diện phải hiển thị điểm cùng độ phủ; không diễn giải score cao là hồ sơ đã đầy đủ bằng chứng. Các artifact LTR đã train với score theo policy cũ không được coi là tương thích với `matching-v2.1` cho tới khi train/đánh giá lại.

## 3. Version phải tăng khi nào

| Thay đổi | Version cần tăng |
|---|---|
| Logic chunk/spec/rule/alias | `DETERMINISTIC_RULES_VERSION` |
| Công thức điểm/coverage/gate/ranking | `MATCHING_POLICY_VERSION` và policy trong DB nếu thay ngưỡng |
| Nội dung matching prompt | `MATCHING_PROMPT_VERSION` |
| Nội dung profile prompt | `PROFILE_PROMPT_VERSION` |
| Nội dung criteria prompt | `CRITERIA_PROMPT_VERSION` |
| Model/endpoint/seed runtime | snapshot runtime tự vào fingerprint; vẫn cần ghi release note |
| Embedding provider/model/dimension/index version/query instruction | semantic config tự vào fingerprint khi bật; tăng `EMBEDDING_INDEX_VERSION` khi đổi không gian vector hoặc cách chunk/index |
| LTR feature schema, trọng số, scaler hoặc metric gate | tạo `model_version` artifact mới; không sửa artifact đã đăng ký/`APPROVED` tại chỗ |

Sau khi tăng version, chạy golden/repeatability, ghi kết quả vào release note rồi mới triển khai. Không dùng lại version cũ cho hành vi mới.

## 4. Đo độ ổn định

Module `backend/app/services/evaluation.py` và CLI `backend/scripts/evaluate_matching.py` cung cấp **diagnostic lịch sử**, không chứng minh acceptance: `passed` trong phép tính library hay Langfuse không đủ thông tin về cohort/rerun/ranking thật. CLI legacy đánh dấu `diagnostic_only`, `passed=false`, và `--check` luôn thoát 2. Với contract snapshot tường minh, xem `doc/OFFLINE_MATCHING_SYNTHETIC.md` và `offline_matching_eval.py repeatability`.

Các metric diagnostic gồm:

- mean/max/P95 độ lệch điểm;
- số lượng và tỉ lệ criterion flip;
- exact application agreement;
- Spearman, Kendall tau-b (có hiệu chỉnh ties) và Top-5/10/20 overlap của ranking;
- tỉ lệ fingerprint reuse nếu được cung cấp số liệu operation.

### 4.1 Định dạng snapshot đầu vào

CLI nhận một list run, hoặc object:

```json
{
  "runs": [
    {
      "application_id": "app-1",
      "matching_score": 90.0,
      "evidence_coverage": 1.0,
      "assessment_fingerprint": "fp-...",
      "criterion_results": [
        {"criterion_id": "criterion-1", "outcome": "MATCH"}
      ]
    }
  ],
  "reuse": {"eligible": 20, "reused": 20},
  "rankings": {
    "baseline": ["app-1", "app-2"],
    "candidate": ["app-1", "app-2"]
  }
}
```

Các run cùng fingerprint được hiểu là forced rerun. Thứ tự thời gian được xác định tường minh bằng `run_index`/`sequence`, sau đó `created_at`; thứ tự trong file chỉ là tie-breaker cuối. Run sớm nhất của mỗi application là baseline, các run sau là rerun. Nếu không cung cấp ranking, CLI suy ranking từ score giảm dần, coverage giảm dần, rồi application_id tăng dần.

Exporter chính thức chỉ đọc `backend/scripts/export_matching_snapshot.py` xuất assessment ID, fingerprint, điểm, coverage, outcome và ranking. Exporter không xuất CV text, profile facts, quote bằng chứng hoặc provider snapshot.

### 4.2 Chạy đo

```bash
cd backend
# Diagnostic lịch sử, không ký nghiệm thu:
.venv/bin/python scripts/evaluate_matching.py /path/to/snapshots.json
# Contract mới, snapshot tường minh và reuse counts:
.venv/bin/python scripts/offline_matching_eval.py repeatability /path/to/paired-snapshots.json --check
```

Legacy `--check` luôn thoát `2`. Contract mới cũng thoát `2` khi FAIL/INSUFFICIENT_DATA hoặc input lỗi; PASS chỉ là đạt ngưỡng tính toán, vẫn cần xác thực provenance và HR review.

### 4.3 Ngưỡng chấp nhận

- Fingerprint reuse: **100%** với cùng fingerprint.
- Forced rerun khác fingerprint nhưng cùng nội dung nghiệp vụ: P95 score drift **≤ 2 điểm**.
- Criterion flip rate: **≤ 2%**.
- Ranking: Kendall tau mục tiêu **≥ 0.90**, Top-10 overlap **≥ 0.90**.
- Mọi `NO_MATCH` bắt buộc và mọi flip của must-have phải được HR review thủ công trước khi phát hành policy mới, kể cả khi tỉ lệ tổng đạt ngưỡng.

## 5. Golden set của HR

Fixture tổng hợp trong repo chỉ là smoke test; không chứng minh chất lượng trên CV thật. Trước pilot mở rộng, HR cần xây golden set riêng:

1. Chọn 50–100 CV đã ẩn danh/được phép sử dụng, đa dạng vị trí, ngôn ngữ EN/VI, PDF/DOCX/OCR, CV ngắn/dài và trường hợp biên.
2. Với từng tiêu chí, hai HR gán độc lập: `STRONG_MATCH`, `MATCH`, `UNCLEAR` hoặc `NO_MATCH`, kèm quote bằng chứng.
3. HR thứ ba/HR Lead phân xử khi hai nhãn khác nhau; lưu lý do phân xử.
4. Tách tập calibration để chỉnh alias/rule và holdout không được dùng chỉnh rule để báo cáo cuối.
5. Không đưa thuộc tính nhạy cảm vào nhãn hoặc dùng chúng làm feature.
6. Mỗi thay đổi rule/prompt/policy phải chạy lại toàn bộ golden set; báo cáo outcome accuracy, false MATCH, false NO_MATCH, unresolved rate và các metric ổn định ở mục 4.

Nền tảng Learning-to-Rank đã có trong mã, nhưng chỉ cân nhắc kích hoạt khi có nhãn HR thật đủ lớn. Ngưỡng bắt đầu đánh giá LTR: vài trăm application đã có quyết định HR nhất quán hoặc đủ cặp so sánh pairwise; LTR chỉ xếp lại trong cùng gate/coverage hợp lệ và không được phá fingerprint/audit trail.

## 6. pgvector/BGE và Learning-to-Rank

### 6.1 Semantic retrieval

Đã có migration `00010_pgvector_bge_ltr.sql` (remote version `20261107022845`) tạo extension `vector`, bảng `app_private.cv_chunk_embeddings`, HNSW cosine index và các cột LTR. Embedding được khóa theo `document_id + chunk_id + chunk_text_sha256 + embedding_model + index_version`; bảng không lưu thêm bản sao raw CV text.

Cấu hình mặc định vẫn an toàn:

```dotenv
SEMANTIC_RETRIEVAL_ENABLED=false
EMBEDDING_PROVIDER=disabled
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_INDEX_VERSION=bge-index-v1
EMBEDDING_API_BASE=
SEMANTIC_TOP_K=5
SEMANTIC_MIN_SIMILARITY=0.35
```

Khi bật, worker embed các chunk của CV và query được tạo từ `requirement_spec`, lưu vector vào pgvector, truy vấn cosine và merge với lexical chunks. Semantic similarity chỉ bổ sung tối đa 5 candidate chunks cho LLM fallback; nó không tạo rule finding, không đổi outcome deterministic và không vượt qua evidence verification. Lỗi provider, lỗi dimension hoặc lỗi pgvector đều fallback về lexical/in-memory. Toàn bộ cấu hình semantic được pin vào assessment fingerprint khi bật.

`EMBEDDING_PROVIDER=hash` chỉ phục vụ test/plumbing, không phải BGE và không được dùng làm bằng chứng chất lượng semantic. Production cần một BGE endpoint thật tương thích `/embeddings`; đổi model có dimension khác 1024 phải có migration mới.

### 6.2 Learning-to-Rank

LTR là pairwise logistic ranker train offline từ ví dụ đã gán nhãn theo group/position. Tập test được tách theo nguyên group/position, không tách ngẫu nhiên từng dòng. Artifact chỉ được dùng khi đạt gate cấu hình:

```dotenv
LTR_MODE=OFF
LTR_MIN_NDCG_AT_10=0.70
LTR_MIN_PAIRWISE_ACCURACY=0.65
LTR_MIN_HOLDOUT_EXAMPLES=20
LTR_MIN_HOLDOUT_GROUPS=2
```

- `OFF`: không tính điểm LTR.
- `SHADOW`: tính và lưu `ltr_score`, không đổi thứ hạng công bố.
- `ACTIVE`: chỉ reorder trong cùng mandatory status và cùng coverage-eligibility gate; không ứng viên nào vượt qua `POSSIBLE_MISMATCH`, trạng thái chưa đánh giá hoặc coverage gate nhờ LTR.

Quy trình vận hành:

```bash
cd backend
.venv/bin/python scripts/export_ltr_dataset.py --output /path/to/ltr_dataset.json
.venv/bin/python scripts/train_ltr.py /path/to/ltr_dataset.json \
  --output /path/to/ltr_model.json --report /path/to/ltr_report.json --check
.venv/bin/python scripts/register_ltr_model.py /path/to/ltr_model.json
```

Exporter chỉ dùng trạng thái ứng tuyển vận hành làm **weak label** và chỉ lấy assessment COMPLETED mới nhất của mỗi application; đây không phải HR gold label. Train script mặc định fail-closed khi có dưới 200 ví dụ hoặc dưới 10 group/position, thiếu mức relevance hoặc không tách được holdout. Register luôn tạo trạng thái `DRAFT`; ACTIVE chỉ dùng artifact đã `APPROVED` trong registry hoặc artifact file đạt gate. Chưa có HR labelled dataset đủ lớn và chưa cấu hình BGE endpoint thật trong môi trường hiện tại, nên không được tuyên bố LTR/BGE production đã được kích hoạt.

## 7. Kiểm thử liên quan

```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/test_deterministic_matching.py \
  backend/tests/test_matching_evaluation.py \
  backend/tests/test_phase1_unit.py \
  backend/tests/test_matching_audit_fixes.py \
  backend/tests/test_semantic_ltr.py
```

Integration test cần PostgreSQL cục bộ dùng một lần theo `backend/tests/README.md`; không chạy chúng trên database production/Supabase thật.
