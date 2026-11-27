# Talent Pool: dữ liệu CV lưu thế nào, và luồng quét khi có vị trí mới

Ngày rà: 2026-11-05. Đọc code tại nhánh `arena/ea6e2570-vinit-hrapp` và kiểm dữ liệu
thật trên Supabase test `myrymlqdbyqmpynesiwk` (chỉ đọc).

## Trả lời ngắn nhất

**Talent Pool không phải một kho riêng.** Nó là **một bảng consent** gắn lên hồ sơ ứng
tuyển đã có. CV nằm nguyên chỗ cũ — gắn với vị trí đã ứng tuyển. Talent Pool chỉ là
"hồ sơ này được phép dùng lại cho vị trí khác".

**Luồng quét hiện tại KHÔNG chấm điểm, KHÔNG xếp hạng, KHÔNG gọi AI.** Nó trả về danh
sách hồ sơ *đủ điều kiện về mặt dữ liệu*, rồi dừng. Nguyên văn trong code:

> `'note': 'Danh sách đủ điều kiện; không phải đánh giá hay xếp hạng.'`

**Và tính năng đang TẮT.** Hai cờ đều mặc định `false`.

---

## 1. Talent Pool lưu cái gì

```sql
CREATE TABLE app_private.talent_pool_consents (
    application_id uuid PRIMARY KEY REFERENCES app_private.applications(...) ON DELETE CASCADE,
    notice_version text NOT NULL,
    token_hash text NOT NULL UNIQUE,          -- sha256 của token rút consent
    accepted_at timestamptz NOT NULL,
    consent_expires_at timestamptz NOT NULL,  -- hết hạn đồng ý
    retention_expires_at timestamptz NOT NULL,-- hết hạn lưu giữ
    withdrawn_at timestamptz                  -- null = còn hiệu lực
);
```

Chỉ có vậy. **Không có bảng CV riêng cho talent pool**, không có bản sao CV, không có
"kho ứng viên" tách khỏi vị trí.

### Hệ quả quan trọng

Một người trong Talent Pool **vẫn thuộc về vị trí họ đã ứng tuyển**. Muốn quét, phải
chọn **hai** vị trí: `source_position_id` (vị trí cũ, nơi hồ sơ đang nằm) và
`target_position_id` (vị trí mới). Không có khái niệm "quét toàn bộ kho".

Điều này ảnh hưởng trực tiếp đến câu hỏi của anh: **muốn tìm người cho vị trí mới, phải
biết họ đã ứng tuyển vị trí nào trước đó.** Không quét chéo được toàn hệ thống.

---

## 2. CV lưu ở đâu, gồm những gì

Bốn lớp, tách theo mục đích:

| Lớp | Bảng | Lưu gì |
|---|---|---|
| **Tệp gốc** | Supabase Storage + `application_documents` | PDF/DOCX gốc; bảng chỉ giữ `bucket`, `storage_path`, `mime_type`, `size_bytes`, trạng thái xử lý |
| **Chữ trích xuất** | `document_processing_runs.extracted_text_storage_path` | Chữ OCR/parse, lưu ở Storage chứ không trong DB |
| **Hồ sơ có cấu trúc** | `profile_versions` + `profile_facts` | `fact_type` ∈ EDUCATION / WORK_EXPERIENCE / SKILL / CERTIFICATION / LANGUAGE / PROJECT; mỗi fact là JSONB + số trang + độ tin cậy |
| **Vector ngữ nghĩa** | `cv_chunk_embeddings` | `vector(1024)`, HNSW index; **không lưu chữ gốc**, chỉ `chunk_id` + `chunk_text_sha256` + vị trí ký tự |

Ghi chú của bảng embedding nói rõ: *"No raw CV text is stored in this table."*

Tất cả đều `ON DELETE CASCADE` từ `applications` — xoá hồ sơ là xoá sạch, kể cả vector.

---

## 3. Luồng quét hiện tại chạy thế nào

### Điều kiện để một hồ sơ lọt vào kết quả

Tất cả phải đúng cùng lúc (`api/talent_pool.py:78-95`):

1. Consent `withdrawn_at IS NULL` — chưa rút
2. `consent_expires_at > now` — đồng ý còn hạn
3. `retention_expires_at > now` — hạn lưu giữ còn
4. Không có `application_retention_cases` đang chạy (trừ `CANCELLED`)
5. Có ít nhất một tài liệu `document_type='CV'` và `file_processing_status='COMPLETED'` — **CV phải xử lý xong**, CV lỗi OCR không lọt
6. Vị trí **nguồn** đang `OPEN` hoặc `PAUSED`
7. Vị trí **đích** phải `OPEN` **và** có bộ tiêu chí `APPROVED` cho JD mới nhất

### Điều kiện về người dùng

- Phải là HR phụ trách **cả hai** vị trí (`_require_hr_locked` với `include_admin=True`)
- Ghi audit `TALENT_POOL_SCAN` mỗi lần quét, có `source_position_id` và số lượng

### Kết quả trả về

```json
{ "items": [{ "application_id", "position_id", "display_name",
              "consent_expires_at", "retention_expires_at" }],
  "next_cursor": "...",
  "note": "Danh sách đủ điều kiện; không phải đánh giá hay xếp hạng." }
```

**Không có điểm số. Không có thứ hạng. Không có lý do khớp.** Chỉ tên và hạn consent.

### Giao diện

`/talent-pool` đã nối sẵn: chọn vị trí nguồn + vị trí đích → bấm "Tìm hồ sơ đủ điều
kiện" → hiện danh sách tên và hạn consent, có phân trang.

---

## 4. Có qua AI không? — Trả lời chính xác

**Luồng quét: KHÔNG.** Không một dòng nào gọi LLM. Đây là truy vấn SQL thuần.

**Luồng chấm điểm (khi hồ sơ đã vào một vị trí): CÓ, nhưng chỉ một phần.** Kiến trúc
trong `workers/processor.py:1355-1420`:

```
1. deterministic_matcher.evaluate_criteria(cv_text, criteria_items, profile)
        ↓
   Rule so khớp từ khoá, số năm, bằng cấp, ngoại ngữ → quyết được phần lớn tiêu chí
        ↓
2. Tiêu chí nào rule KHÔNG giải quyết được  →  unresolved_criteria
        ↓
3. Chỉ với nhóm này: semantic retrieval (BGE) lấy thêm đoạn liên quan
        ↓
4. Chỉ với nhóm này: llm_client.match_criterion_evidence(...)  ← AI
        ↓
5. evidence_verification: kiểm trích dẫn có thật trong CV
```

Nguyên văn comment trong code:

> Deterministic rules decide measurable criteria first. The LLM is only a fallback for
> criteria the rules cannot decide, and it receives just that unresolved sub-rubric.

Vậy: **phần lớn là so tiêu chí bằng rule, AI chỉ xử lý phần rule bó tay.** Không phải AI
đọc toàn bộ CV rồi chấm điểm tổng thể.

### Ba cờ phải bật thì mới có phần AI/ngữ nghĩa

| Cờ | Mặc định | Bật thì được gì |
|---|---|---|
| `TALENT_POOL_STORAGE_READY` | `false` | Toàn bộ API talent pool trả 404 |
| `TALENT_POOL_REDISCOVERY_ENABLED` | `false` | Riêng `/scan` trả 404 |
| `SEMANTIC_RETRIEVAL_ENABLED` | `false` | BGE vector tìm đoạn liên quan cho AI |

`LTR_MODE` mặc định `"OFF"` — không có học xếp hạng.

**Lưu ý:** tắt `SEMANTIC_RETRIEVAL_ENABLED` **không** làm hỏng chấm điểm, chỉ làm phần
AI kém chính xác hơn (thiếu ngữ cảnh). Rule vẫn chạy.

---

## 5. Trạng thái thật trên Supabase test

Kiểm trực tiếp, **tất cả bằng 0**:

```
applications              0
application_documents     0
profile_versions          0
profile_facts             0
cv_chunk_embeddings       0
talent_pool_consents      0
storage.objects           0
```

Nên hiện tại **không có CV nào trong hệ thống**, kể cả talent pool. Mọi câu hỏi về luồng
quét hiện là lý thuyết cho tới khi anh tải CV thật.

---

## 6. Vì sao luồng quét cố ý không chấm điểm

Đây là quyết định thiết kế, đọc được từ ba chỗ:

**a) Nội dung thông báo trong code** — cả API lẫn giao diện đều nói rõ "không phải đánh
giá hay xếp hạng", và nhắc *"Hãy tìm lại trước khi sử dụng: consent có thể đã rút hoặc hết
hạn sau lần tìm trước."*

**b) Chấm điểm đòi hỏi rubric đã duyệt.** Điều kiện 7 ở trên: vị trí đích phải có bộ tiêu
chí `APPROVED`. Tức muốn so tiêu chí cho người từ talent pool, trước hết vị trí mới phải
có rubric duyệt xong.

**c) Consent có thời hạn, và hết hạn thì không được dùng.** Chấm điểm là "dùng". Nếu scan
tự chấm điểm rồi cache lại kết quả, một hồ sơ hết hạn consent sẽ vẫn còn điểm trong DB —
tức dùng dữ liệu quá hạn. Đây là lý do phải **tìm lại mỗi lần**, không lưu kết quả scan.

---

## 7. Nếu muốn nối "quét → chấm điểm" thì phải làm gì

Hiện **chưa có** luồng này. Ba mảnh đã có sẵn để ghép:

| Đã có | Ở đâu |
|---|---|
| Danh sách hồ sơ đủ điều kiện | `GET /talent-pool/scan` |
| Chấm điểm một hồ sơ theo rubric đã duyệt | worker + `deterministic_matcher` + LLM fallback |
| Chặn theo consent còn hạn | cùng truy vấn scan |

**Còn thiếu ba thứ — và cả ba đều là quyết định, không phải code:**

1. **Consent có cho phép chấm điểm không.** Đồng ý "được liên hệ lại" khác "được đem CV
   đi chấm điểm". Cần một câu rõ trong thông báo consent, và nếu khác nhau thì phải có
   **hai loại consent**.
2. **Có ghi điểm vào DB hay không.** Nếu ghi, phải có cơ chế xoá khi consent hết hạn —
   nếu không thì điểm tồn tại lâu hơn quyền dùng dữ liệu.
3. **Có tính vào xếp hạng chính thức của vị trí không.** Nếu có, người từ talent pool chen
   vào cùng bảng xếp hạng với người nộp đơn mới — cần quyết định có công bằng không, và
   ghi rõ nguồn gốc trong báo cáo.

Đề xuất thứ tự: làm (1) trước. Hai cái sau phụ thuộc câu trả lời của (1).

---

## 8. Một điểm cần cân nhắc khi mở rộng

Truy vấn scan **buộc phải chọn vị trí nguồn**. Nếu HR muốn hỏi "trong toàn bộ talent pool
có ai hợp với vị trí này không", hiện **không làm được** — phải thử từng vị trí nguồn một.

Đây là hệ quả trực tiếp của thiết kế "talent pool là consent gắn lên application, không
phải kho riêng". Muốn quét toàn kho thì phải:

- bỏ `source_position_id` khỏi điều kiện, **và**
- kiểm lại quyền: hiện `_require_hr_locked` chạy trên **cả hai** vị trí. Bỏ vị trí nguồn
  nghĩa là HR chỉ cần quyền trên vị trí đích, tức **đọc được hồ sơ của vị trí họ không
  phụ trách** — đây là thay đổi phân quyền, không phải thay đổi truy vấn.

Việc này nên là một ticket riêng có review bảo mật, không nên gộp vào lúc nối luồng.
