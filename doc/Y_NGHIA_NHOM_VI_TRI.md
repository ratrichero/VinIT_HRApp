# "Nhóm vị trí" trong màn tạo vị trí — có ý nghĩa gì, có quan trọng không

> Đọc từ code ngày 2026-11-30, bản `32b7874`.

## Trả lời ngắn

**Quan trọng, nhưng chỉ với MỘT việc: Thư viện rubric.** Bỏ trống thì hệ thống
vẫn chạy bình thường, chỉ là mất khả năng dùng thư viện rubric — và mất luôn khả
năng **ngăn áp nhầm rubric của nhóm khác**.

Nó **không** ảnh hưởng tới: sinh tiêu chí bằng AI, chấm điểm, xếp hạng, luồng
duyệt, lịch phỏng vấn, hay bất kỳ trạng thái hồ sơ nào.

---

## 1. Nó là gì trong dữ liệu

```
app_private.job_families (bảng riêng, có is_active)
        ↑ job_family_id
app_private.positions
        ↑ job_family_id  (NOT NULL)
app_private.rubric_templates  →  rubric_template_versions  →  rubric_template_items
```

Nhóm vị trí là **cột neo** của thư viện rubric. Mỗi mẫu rubric **bắt buộc** thuộc
một nhóm (`rubric_templates.job_family_id NOT NULL`), và điểm vào thư viện là chọn
nhóm trước.

Hai nhóm có sẵn từ `00023`: `IT & Digital`, `Vận hành & Hành chính`. Admin thêm được.

## 2. Ba việc nó THẬT SỰ điều khiển

| # | Việc | Bằng chứng |
|---|---|---|
| 1 | **Lọc thư viện rubric theo nhóm** — màn chọn rubric xếp mẫu cùng nhóm lên đầu, đánh dấu đỏ "(khác nhóm vị trí)" cho mẫu khác nhóm | `positions/new/page.tsx:303-306` |
| 2 | **Chặn áp rubric khác nhóm ở tầng API** — không có cờ `allow_other_family` thì trả **409** | `rubric_library.py:281-289` |
| 3 | **Sinh rubric từ JD cần biết nhóm** — bỏ trống thì trả **400**: *"Vị trí chưa chọn Nhóm vị trí. Gán nhóm rồi thử lại."* | `rubric_library.py:408-412` |

Việc 2 là lý do chính nên chọn nhóm. Nguyên văn comment trong code:

> Giao diện đã xếp rubric cùng nhóm lên đầu và dán nhãn đỏ, nhưng API vẫn nhận —
> nghĩa là gọi thẳng API vẫn áp được bộ tiêu chí vận hành cho một vị trí kỹ thuật.
> Sai từ gốc và không ai phát hiện cho tới lúc chấm điểm.

## 3. Những gì nó KHÔNG điều khiển (đã kiểm, không suy đoán)

| Không ảnh hưởng | Bằng chứng |
|---|---|
| Sinh tiêu chí bằng AI | `criteria.py` không đọc `job_family` lần nào; prompt chỉ đọc nội dung JD |
| Chấm điểm và xếp hạng | `matching.py`, `assessments.py` không đọc `job_family` |
| Luồng duyệt HR–HM | không đọc |
| Lịch phỏng vấn, phiếu chấm, thông báo | không đọc |
| Trạng thái hồ sơ | không đọc |

Chỉ **hiển thị**: trang `/careers` join sang để hiện tên nhóm cho ứng viên.

## 4. Bỏ trống thì sao — cụ thể

Trường là **tùy chọn** cả ở giao diện (`label={t('Nhóm vị trí (tùy chọn)')}`) và ở
API (`job_family_id: Optional[UUID] = None`).

| Việc | Bỏ trống |
|---|---|
| Tạo vị trí | ✅ được |
| Sinh tiêu chí AI | ✅ được |
| Tải CV, chấm điểm, xếp hạng | ✅ được |
| Duyệt tiêu chí | ✅ được |
| Chia sẻ shortlist, lịch PV, phiếu chấm | ✅ được |
| **Áp rubric từ thư viện** | ❌ **400** — không lọc được, không biết mẫu nào thuộc nhóm nào |
| **Ngăn áp nhầm rubric khác nhóm** | ❌ mất tác dụng — vị trí không có nhóm thì không có gì để so |

Giao diện đã cảnh báo đúng điều này ở màn tạo vị trí:

> Chưa chọn Nhóm vị trí nên thư viện không lọc được theo nhóm. Nên chọn nhóm ở
> bước 1 để tránh áp nhầm rubric của nhóm khác.

## 5. Nên chọn thế nào

| Tình huống | Nên làm |
|---|---|
| Có dùng Thư viện rubric | **Chọn nhóm.** Không chọn thì cả tính năng thư viện vô dụng với vị trí đó |
| Chỉ sinh tiêu chí bằng AI từ JD | Chọn cũng tốt nhưng không bắt buộc |
| Vị trí chưa rõ thuộc nhóm nào | Để trống rồi gán sau bằng "Chỉnh sửa vị trí" — API có `PATCH /v1/positions/{id}` cho phép gán |

## 6. Một điểm chưa tốt (nên sửa khi chia việc cho agent)

Trường này **tùy chọn**, nhưng hệ quả của việc bỏ trống lại **không nhìn thấy được**
cho tới khi HR vào thư viện rubric và bị 400. Cảnh báo hiện có chỉ hiện ở màn tạo
vị trí, và chỉ hiện khi người dùng đã mở tab chọn rubric.

Hai cách sửa, tôi nghiêng về cách 2:

1. Bắt buộc chọn nhóm khi tạo vị trí. **Không nên**: nhiều vị trí không dùng thư
   viện, bắt buộc sẽ làm chậm luồng tạo.
2. Giữ tùy chọn, nhưng **hiện cảnh báo ngay trên trang chi tiết vị trí** khi
   `job_family_id IS NULL` — "Vị trí chưa có nhóm, thư viện rubric sẽ không dùng
   được" kèm nút gán. Như vậy người dùng biết trước khi cần, không phải sau.

Đã ghi vào danh sách việc nhỏ cho agent (không chặn buổi test).
