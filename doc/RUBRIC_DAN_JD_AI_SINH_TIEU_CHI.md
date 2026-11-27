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

## Điều kiện để AI thực sự chạy

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

## Chỗ còn yếu — đề xuất sửa

Tính năng dùng được, nhưng có bốn chỗ đáng cải thiện. **Chưa sửa trong lượt này** vì cần
anh quyết định phạm vi.

### a) Prompt thiên về JD tiếng Anh — **quan trọng nhất**

Nguyên văn dòng 593:

> The JD is expected to be in English and most JDs will be English. Vietnamese JDs are
> supported as an option, not as the default

Với một trường đại học Việt Nam, **mặc định đó ngược**. Thiết kế đã cố ý: dòng 604 yêu cầu
giữ nguyên ngôn ngữ JD ("a Vietnamese JD yields Vietnamese criteria text"), nên JD tiếng
Việt vẫn ra tiêu chí tiếng Việt. Nhưng câu mở đầu vẫn đẩy model về phía tiếng Anh —
cùng loại lỗi với `lang='eng'` của OCR đã sửa.

Đề xuất: đảo thành "JD có thể là tiếng Việt hoặc tiếng Anh; đọc theo đúng ngôn ngữ của nó,
mặc định tiếng Việt". Sửa prompt nghĩa là **tăng `CRITERIA_PROMPT_VERSION`** để log biết
bộ tiêu chí nào sinh ra từ prompt nào.

### b) Không có test nào kiểm JD tiếng Việt đầu-cuối

Test hiện tại chỉ đọc mã nguồn (kiểm có `INSERT` hay không, có `PASTED-JD` hay không).
Không có test nào chạy một JD tiếng Việt qua `_draft_from_jd_text` rồi kiểm:
nhãn `MUST_HAVE` còn nguyên tiếng Anh, nội dung ra tiếng Việt, trọng số cộng 100.

Rủi ro cụ thể: model trả `"Bắt buộc"` thay vì `"MUST_HAVE"` → `coerce_category` phải đoán.
Nếu đoán sai, toàn bộ tiêu chí bắt buộc rơi vào nhóm ưu tiên và điểm số sai âm thầm.
`rubric_normalizer` có xử lý việc này, nhưng **không có test khoá nó lại**.

### c) Lỗi AI hiện không phân biệt được nguyên nhân

Mọi lỗi LLM đều thành một câu: *"Không thể sinh rubric bằng AI. Vui lòng kiểm tra cấu
hình và thử lại."* Ba nguyên nhân rất khác nhau bị gộp làm một:

- chưa bật `ALLOW_EXTERNAL_API` → sửa ở `.env`
- sai/hết hạn API key → sửa trong Admin → AI
- model trả JSON hỏng → bấm lại có thể được

HR đọc câu đó không biết phải làm gì, và **không tự sửa được cái nào** — cả ba đều là việc
của Admin. Đề xuất: trả mã lỗi riêng cho từng trường hợp, và với hai trường hợp đầu thì
nói thẳng "báo Quản trị viên" thay vì "thử lại".

### d) Không có nút dùng lại JD của vị trí khác

Muốn dựng rubric cho "Backend Engineer" khi đã có vị trí "Backend Engineer (cũ)" thì phải
mở vị trí cũ, copy JD, quay lại dán tay. Đường "Sinh từ JD của một vị trí" làm được việc
này nhưng nó **gắn chặt với vị trí đó** — rubric sinh ra mang tên vị trí cũ.

Đây là thiếu sót nhỏ, không chặn. Ghi lại để cân nhắc.

---

## Kết luận

| Câu hỏi | Trả lời |
|---|---|
| Có nên tích hợp? | **Đã tích hợp rồi**, từ trước. Không cần làm thêm. |
| Có nên dùng không? | **Nên** — nhanh hơn gõ tay nhiều lần, và AI chỉ đề xuất chứ không tự lưu |
| Rủi ro chính? | JD tiếng Việt có thể bị prompt đẩy về tiếng Anh (mục a) |
| Trước khi dùng cần gì? | `ALLOW_EXTERNAL_API=true` trong `.env` backend, rồi khởi động lại |
| Kiểm thế nào? | Admin → AI → kiểm tra kết nối; hoặc dán thử một JD, xem có ra tiêu chí không |

Đường đi khi anh test: **/rubrics → Sinh từ JD dán tay → chọn nhóm → dán JD → Sinh nháp
→ rà → Lưu bản nháp → `hr@vinuni.edu.vn` xuất bản**.
