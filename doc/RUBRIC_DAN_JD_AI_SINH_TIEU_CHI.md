# Có nên dùng "dán JD → AI sinh tiêu chí" ở thư viện rubric?

Ngày 2026-11-05. Rà trên code nhánh `arena/ea6e2570-vinit-hrapp` và cấu hình AI thật
trong Supabase test `myrymlqdbyqmpynesiwk` (chỉ đọc).

## Trả lời ngắn

**Nên dùng — và tính năng này đã có sẵn rồi.** Không phải việc cần làm thêm.

Anh chưa thấy nó vì **cùng một lỗi quyền vừa sửa**: cả bốn nút tạo rubric (trong đó có
nút "Sinh từ JD dán tay") nằm trong `{capabilities.can_create && ...}`, mà `can_create`
trả `false` cho tài khoản ADMIN. Sửa xong ở commit `ab03b44`, nay nút hiện ra.

---

## Tính năng có những gì

Hai biến thể, không phải một:

| Nút | Đầu vào | Cần gì trước |
|---|---|---|
| **Sinh từ JD dán tay** | Anh dán text JD vào hộp | Không cần gì — không cần vị trí, không cần JD lưu sẵn |
| **Sinh từ JD của một vị trí** | Chọn một vị trí đã có | Vị trí đó phải có JD **và** đã gán Nhóm vị trí |

Với tình huống hiện tại của anh (0 vị trí trong DB), **chỉ đường "dán tay" dùng được** —
và nó đúng là đường phù hợp nhất: dựng rubric mẫu trước khi mở vị trí.

### Luồng thực tế

1. Bấm **"Sinh từ JD dán tay"**
2. Chọn **Nhóm vị trí** (bắt buộc — quyết định rubric dùng lại được cho vị trí nào)
3. Đặt tên rubric (tùy chọn; bỏ trống thì thành "Nháp từ JD dán tay")
4. Dán JD (tối thiểu 50 ký tự, tối đa 100.000)
5. Bấm **"Sinh nháp"** → chờ AI
6. AI trả về bộ tiêu chí **điền vào biểu mẫu**, chia sẵn MUST_HAVE / NICE_TO_HAVE, trọng
   số đã chuẩn hoá về 100 mỗi nhóm, kèm 3–5 từ khoá bằng chứng mỗi tiêu chí
7. HR **sửa** nếu cần → **Lưu bản nháp**
8. **HR_LEAD xuất bản** → rubric mới hiện trong hộp "Dùng rubric đã xuất bản" ở trang vị trí

---

## Vì sao thiết kế này đúng

Bốn quyết định trong code đáng giữ nguyên, đừng "cải tiến" cho nhanh hơn:

**1. AI chỉ điền biểu mẫu, không lưu.** Endpoint `suggest-from-jd` không có một câu
`INSERT`/`UPDATE`/`DELETE` nào — có test khoá điều này
(`test_rubric_from_pasted_jd.py:30`). Không ghi thẳng vào thư viện, vì model sai một tiêu
chí là cả thư viện nhiễm bẩn và không ai nhớ để dọn.

**2. JD dán tay không bị lưu vào `jd_versions`.** Nó chỉ là nguyên liệu cho model đọc.
Không tạo rác gắn với vị trí không tồn tại.

**3. Bỏ tiêu chí hỏng, không bỏ cả bộ.** Model trả 12 tiêu chí mà 1 cái sai định dạng
thì giữ 11 cái kia, **đếm số bị bỏ và báo lại** cho HR biết bộ nháp đã bị cắt. Bỏ cả bộ
vì một lỗi là bắt HR bấm lại từ đầu.

**4. Chặn nội dung phân biệt đối xử ngay trong prompt.** Dòng 602 của `llm_client.py`:
cấm sinh tiêu chí về tuổi, giới tính, tình trạng hôn nhân, quốc tịch, ngoại hình, tính
cách. Cộng với `redact_text()` che PII trước khi gửi.

Ngoài ra còn hai thứ dễ bị bỏ qua nhưng có ích: **nháp tự lưu vào trình duyệt** (đóng tab
không mất, mở lại hỏi khôi phục) và **chặn rời trang khi có thay đổi chưa lưu**.

---

## Điều kiện để AI thực sự chạy (vẫn đúng, chưa đổi)

Tính năng có trong code **không** có nghĩa là nó chạy được trên VPS của anh. Kiểm DB thật:

```
ai_configuration_versions: 1 bản ACTIVE
  provider      = compatible
  provider_name = Top Tool AI
  model         = Top-Tools-Ai-Pro
  api_base      = https://top-tools-ai.com/api/v1
  có API key    = true (••••6ad3)
```

Vậy đã có cấu hình LLM đang bật với khoá thật. Nhưng còn **hai chốt chặn ở tầng môi
trường** mà Admin UI **không** bật hộ được:

### Chốt 1 — `ALLOW_EXTERNAL_API=true`

`llm_client.py:233-251` từ chối mọi endpoint ngoài trừ khi bật cờ này:

```python
if settings.ALLOW_EXTERNAL_API and parsed.scheme == "https":
    return
...
raise LLMError("External AI endpoints are disabled by configuration")
```

`top-tools-ai.com` là endpoint ngoài, nên **thiếu cờ này là 503**: *"Không thể sinh rubric
bằng AI. Vui lòng kiểm tra cấu hình và thử lại."*

Đây là fail-closed có chủ ý: không gửi dữ liệu ứng viên ra ngoài khi chưa được phép rõ
ràng. Admin UI có hiện cảnh báo (`admin/page.tsx:291`) nhưng **không bật được thay anh** —
phải đặt trong `.env` của backend rồi khởi động lại.

### Chốt 2 — `AI_CONFIG_ENCRYPTION_KEY`

Có sẵn trong biến môi trường thì API key mã hoá được lưu đúng. DB đã có ciphertext nên
nhiều khả năng chốt này đã qua — nhưng nếu đổi khoá thì mọi key đã lưu thành không đọc
được.

### Cách kiểm nhanh

Vào **Admin → AI**, bấm nút kiểm tra kết nối. Xanh là gọi được; đỏ thì xem mã lỗi.

---

## Chỗ còn yếu — trạng thái sau khi sửa (a), (b), (c)

### a) Prompt thiên về JD tiếng Anh — **ĐÃ SỬA** (`2ec87a2`)

Câu mở đầu cũ:

> The JD is expected to be in English and most JDs will be English. Vietnamese JDs are
> supported as an option, not as the default

Nay đảo thành mặc định tiếng Việt, vẫn giữ nhánh xử lý JD tiếng Anh. Câu mới nói rõ: đọc
JD theo đúng ngôn ngữ của nó, không dịch trước; JD tiếng Anh thì output tiếng Anh, JD
tiếng Việt thì output tiếng Việt.

Prompt này **dùng chung** cho cả `criteria.py` (sinh tiêu chí cho một vị trí) và
`rubric_library.py` (sinh nháp thư viện), nên sửa một chỗ cải thiện cả hai luồng — không
chỉ thư viện rubric.

`CRITERIA_PROMPT_VERSION`: `criteria-prompt-v2.1` → **`criteria-prompt-v2.2`**.

### b) Test khoá prompt và test đầu-cuối cho đường dán JD — **ĐÃ SỬA** (`2ec87a2`)

Đánh giá ban đầu của tôi ở đây **sai một phần**: `rubric_normalizer` đã có test tiếng Việt
từ trước (`test_rubric_suggest.py:18`), và `suggest_from_position` đã có test đầu-cuối với
JD tiếng Việt. Chỗ thực sự trống là hai cái khác:

**1. Không có test nào đọc nội dung prompt.** Đổi prompt thành gì cũng không có gì đỏ —
nên câu "most JDs will be English" nằm đó bao lâu cũng không ai biết. Nay có
`test_criteria_prompt_language.py` (6 test) khoá: tiếng Việt là mặc định, câu cũ không
được quay lại, JD tiếng Anh vẫn xử lý đúng, enum `MUST_HAVE`/`NICE_TO_HAVE` không được
dịch, chốt chặn nội dung phân biệt đối xử còn nguyên, JD được bọc là `untrusted`, và
version đã bump.

**2. Đường dán JD không có test đầu-cuối.** Đây là đường **duy nhất dùng được khi chưa có
vị trí nào** — tức đúng đường anh sẽ dùng. Test cũ chỉ kiểm đường `suggest_from_position`.
Nay có 2 test mới: JD tiếng Việt cho nội dung tiếng Việt + enum tiếng Anh + trọng số
`"70%"` đọc đúng và cộng 100 mỗi nhóm; và toàn bộ tiêu chí hỏng thì 502 chứ không trả danh
sách rỗng.

Đã kiểm ngược cả hai: khôi phục prompt cũ → 1 test đỏ; gỡ alias `"bắt buộc"` →
3 test đỏ.

### c) Lỗi AI nói được nguyên nhân — **ĐÃ SỬA** (`121601b`)

Trước: mọi lỗi AI ra một câu *"Không thể sinh rubric bằng AI. Vui lòng kiểm tra cấu hình
và thử lại."* — gộp ba tình huống đòi ba hành động khác hẳn, và HR **không có quyền sửa**
hai trong ba.

Gốc rễ không phải thiếu thông tin. `_call_llm_one` đã phân loại sẵn (`failure_category`)
và test-kết-nối đã có `error_code`. Gốc rễ là hai chỗ:

1. `class LLMError(Exception): pass` — không mang mã nào.
2. `_call_llm` ném lại `"All configured LLM routes failed"` khi thử hết route — **xoá luôn**
   thứ vừa phân loại được.

Nay `LLMError` mang `code` (mặc định `None`, không phải một mã chung — chưa phân loại được
thì nói là chưa), và câu thông báo chia theo **việc HR phải làm**:

| Nhóm | Mã | Câu cho HR |
|---|---|---|
| **Báo Quản trị viên** | `POLICY_BLOCKED` | chưa bật `ALLOW_EXTERNAL_API` trong `.env` máy chủ |
| | `AUTH_FAILED` | khoá API sai, bị thu hồi hoặc hết hạn |
| | `CONFIG_MISSING` / `CONFIG_INVALID` / `NOT_FOUND` | chưa cấu hình / sai địa chỉ / sai tên model |
| **Thử lại** | `RATE_LIMITED` | bị giới hạn tốc độ, chờ rồi bấm lại |
| | `TIMEOUT` / `NETWORK_ERROR` / `PROVIDER_ERROR` | mạng hoặc nhà cung cấp chập chờn |
| | `INVALID_JSON` | AI trả JSON hỏng, thường chỉ một lần |

`str(exc)` **không** được dùng làm thông báo: chuỗi đó có thể chứa status HTTP, địa chỉ
endpoint, tên model — chỉ vào log.

**Một lỗi thật phát hiện thêm:** `_check_endpoint_policy` nằm trong `_call_llm_one`, mà
hàm đó có `@retry` 3 lần. Lỗi cấu hình **tất định** bị retry vô ích — đo thực tế **4.02
giây** chờ rồi vẫn nhận đúng lỗi đó. Nay `_is_retryable()` loại `POLICY_BLOCKED`,
`CONFIG_*`, `AUTH_FAILED`, `NOT_FOUND` khỏi retry (0.01s); lỗi mạng và 5xx vẫn retry 3
lần như cũ.

**Bài học đáng ghi lại:** test đầu tiên tôi viết **không** bắt được việc gỡ retry, vì nó
đếm số request — mà `_check_endpoint_policy` chặn *trước khi mở kết nối*, nên số request
luôn bằng 0 dù có retry hay không. Phải đo **thời gian chờ** mới phân biệt được. Một test
"xanh" không có nghĩa là nó kiểm đúng thứ mình tưởng.

### d) Gợi ý (CHƯA LÀM): nút "Lấy JD từ vị trí khác"

Muốn dựng rubric cho "Backend Engineer" khi đã có vị trí "Backend Engineer (cũ)" thì phải
mở vị trí cũ, copy JD, quay lại dán tay. Đường "Sinh từ JD của một vị trí" làm được nhưng
rubric sinh ra **mang tên vị trí cũ**.

Tin tốt: **API đã trả sẵn nội dung JD.** `GET /positions/{id}/jd-versions` trả về
`content_text` (`positions.py:563-572`). Nên đây không phải việc backend, chỉ là thiếu một
nút nối hai màn hình.

Đề xuất (nhỏ hơn (c)): trong hộp "Sinh từ JD dán tay", thêm một hộp chọn **"Hoặc lấy JD từ
vị trí có sẵn"**:

1. Chọn vị trí → gọi `positionsApi.getJdVersions(id)` → lấy bản mới nhất → **đổ vào ô
   `jdText`**, để HR thấy và sửa được trước khi bấm "Sinh nháp".
2. **Không** tự đổi nhóm: nhóm vẫn do HR chọn, vì đây là rubric **mới** chứ không phải
   rubric của vị trí cũ. Có thể gợi ý nhóm của vị trí đó nhưng không khoá.
3. Tên rubric vẫn để trống cho HR đặt — đừng lấy tên vị trí cũ, đó chính là cái đang gây
   nhầm lẫn.

Vì sao đổ vào ô chứ không gọi thẳng API: HR phải thấy mình đang đưa cái gì cho AI, và sửa
được. Đó cũng là lý do toàn bộ luồng này giữ nguyên tắc "AI chỉ điền biểu mẫu".

---

## Kết luận

| Câu hỏi | Trả lời |
|---|---|
| Có nên tích hợp? | **Đã tích hợp rồi**, từ trước. Không cần làm thêm. |
| Còn phải làm gì? | Chỉ bật `ALLOW_EXTERNAL_API=true` ở `.env` backend. Code đã sẵn sàng. |
| Có nên dùng không? | **Nên** — nhanh hơn gõ tay nhiều lần, và AI chỉ đề xuất chứ không tự lưu |
| Rủi ro chính? | ~~JD tiếng Việt bị prompt đẩy về tiếng Anh~~ — **đã sửa** (`2ec87a2`, prompt v2.2) |
| Trước khi dùng cần gì? | `ALLOW_EXTERNAL_API=true` trong `.env` backend, rồi khởi động lại |
| Kiểm thế nào? | Admin → AI → kiểm tra kết nối; hoặc dán thử một JD, xem có ra tiêu chí không |
| Nếu AI lỗi? | Từ `121601b` câu lỗi nói rõ **báo Quản trị viên** hay **thử lại**, không còn câu chung |

Đường đi khi anh test: **/rubrics → Sinh từ JD dán tay → chọn nhóm → dán JD → Sinh nháp
→ rà → Lưu bản nháp → `hr@vinuni.edu.vn` xuất bản**.
