# Thư viện rubric đang là tính năng chết — nguyên nhân và cách sửa

Ngày rà: 2026-11-05. Rà trên code tại nhánh `arena/ea6e2570-vinit-hrapp` **và** trên
dữ liệu thật của Supabase test `myrymlqdbyqmpynesiwk` (chỉ đọc).

Kết luận ngắn: **anh nói đúng — tính năng chết.** Nhưng không phải một lỗi, mà **bốn**
lỗi độc lập chồng lên nhau. Sửa một cái không đủ để tính năng sống.

---

## Bốn nguyên nhân, xếp theo mức chặn

### 1. `can_create` không tính ADMIN — **đã sửa**

`backend/app/api/rubric_library.py:132` (trước khi sửa):

```python
return {'can_create': bool(assigned or roles.intersection({'HR_RECRUITER', 'HR_LEAD'})), ...}
```

Tài khoản của anh là `adhra@vinuni.edu.vn`, role **duy nhất** là `ADMIN` (kiểm trực tiếp
trong `user_role_assignments`). Vậy `can_create` trả về `False`.

Hệ quả trên giao diện: bốn nút tạo rubric nằm trọn trong `{capabilities.can_create && (...)}`.
`false` → **cả cột trái không render gì**, chỉ còn dòng chữ "Chưa có rubric nào." Không
nút, không menu, không đường nào đi tiếp. Đúng hiện tượng anh thấy.

Đây là **lỗi**, không phải thiết kế. Mọi endpoint phân quyền khác trong hệ thống đều đã
tính ADMIN:

| File | Dòng | Có ADMIN |
|---|---|---|
| `positions.py` | 118 | ✅ |
| `scorecards.py` | 90, 143 | ✅ |
| `dashboard.py` | 38 | ✅ |
| `shortlist.py` | 200 | ✅ |
| `interviews.py` | 138 | ✅ |
| `jd_import.py` | 26 | ✅ |
| `rubric_library.py` | **132** | ❌ **bỏ sót** |

Ngược đời hơn: ADMIN **là người duy nhất** tạo được nhóm vị trí (`job_families.py:70` yêu
cầu đúng `role_code = 'ADMIN'`). Tức ADMIN cấu hình được cái neo của thư viện rubric
nhưng không tạo được rubric nào trong đó.

Cùng lỗi ở `_require_editor` (`:92`): dù có sửa `can_create`, POST vẫn 403 vì
`_require_editor` cần `HR_LEAD` hoặc (`assigned`/`HR_RECRUITER` + là owner).

**Đã sửa cả hai chỗ.** `can_publish` **giữ nguyên chỉ `HR_LEAD`** — xuất bản vẫn là quyền
riêng của Trưởng nhóm HR, đúng thiết kế trong `doc/HUONG_DAN_RUBRIC.md:199` và
`doc/PHASE2_IMPLEMENTATION_PLAN.md:234`.

> ### Sửa lại lần hai (`a4745f7`) — quyết định trên là sai
>
> Giữ `can_publish` chỉ cho `HR_LEAD` tạo ra đúng một nửa lỗi: **ADMIN tạo được bản nháp
> rồi không bao giờ xuất bản được chính nó**, mà người tạo rubric ít ai là HR_LEAD. Lúc
> báo lỗi, anh gặp đúng tình huống này.
>
> Nay `can_publish` = `{ADMIN, HR_LEAD}`, khớp với mọi chốt phân quyền khác trong hệ
> thống. `HR_RECRUITER` vẫn 403. Hai biểu thức (`capabilities` và endpoint `publish`) phải
> khớp **tuyệt đối** — lệch nhau thì giao diện hiện nút rồi bấm vào 403; có test riêng
> khoá sự khớp này vì chúng nằm cách nhau gần 100 dòng.

### 2. Không có rubric mồi nào — **đúng thiết kế, không sửa**

Kiểm DB thật:

```
rubric_templates          = 0
rubric_template_versions  = 0
job_families (is_active)  = 2
positions                 = 0
```

`doc/PHASE2_IMPLEMENTATION_PLAN.md:57` ghi rõ quyết định **D-01**:

> Chỉ hai nhóm đầu: IT & Digital và Vận hành & Hành chính; **chưa có nội dung rubric
> nghiệp vụ, không seed nội dung**

Vậy thư viện rỗng là **cố ý** — rubric là thước đo do HR nghiệp vụ viết, không phải thứ
lập trình viên bịa ra rồi seed vào. Nhưng khi ghép với lỗi 1, "rỗng cố ý" + "không có nút
tạo" = tính năng chết. Rỗng thì không sao, miễn có đường tự dựng.

Lệnh purge test data **không** xoá rubric mẫu (không có bảng `rubric_*` nào trong
`DELETE_ORDER` của `test_data_purge.py`) — nên rubric anh tạo sẽ sống qua các lần purge.

### 3. Luồng "Sinh từ JD của một vị trí" cần vị trí đã có nhóm

`rubrics/page.tsx:149`:

```javascript
setSuggestPositions(res.filter((item: any) => item.job_family_id));
```

Vị trí chưa gán nhóm **bị lọc khỏi hộp chọn**. Với DB hiện tại `positions = 0` nên hộp
này rỗng và hiện thông báo "Chưa có vị trí nào được gán Nhóm vị trí."

Đây là **cố ý** (rubric không nhóm thì không tái sử dụng được), nhưng nó có nghĩa: đường
này **không dùng được** cho tới khi có vị trí + vị trí đó có nhóm. Hai đường còn lại thì
dùng được ngay:

- **Tạo rubric nháp** — biểu mẫu trống, không cần gì.
- **Sinh từ JD dán tay** — dán text JD, chọn nhóm, AI đề xuất. Không cần vị trí.

### 4. Không có đường nào nhắc HR rằng thiếu nhóm — **đã thêm**

Trường tùy chọn ở cả UI lẫn API. HR tạo vị trí, bỏ qua nhóm, mọi thứ chạy bình thường
cho tới lúc vào thư viện rubric và không hiểu vì sao vị trí không có trong danh sách.

---

## Đã sửa gì trong lượt này

| File | Thay đổi |
|---|---|
| `backend/app/api/rubric_library.py` | `can_create` + `_require_editor` tính ADMIN; `can_publish` giữ nguyên HR_LEAD |
| `backend/tests/test_phase2_workflow.py` | thêm `test_admin_can_build_rubric_library_but_not_publish` — khoá cả hai chiều: ADMIN tạo được, ADMIN **không** xuất bản được |
| `frontend/src/app/rubrics/page.tsx` | khi `can_create = false` hiện cảnh báo nêu rõ cần vai trò nào, thay vì im lặng |
| `frontend/src/app/positions/[id]/page.tsx` | cảnh báo khi `job_family_id` trống, kèm nút "Gán nhóm" mở luôn hộp sửa |

Kiểm: backend **673 passed / 175 skipped**, ruff `--select F` sạch, `tsc` sạch, ESLint
sạch, test FE **183/183**. Test mới là integration test nên **chỉ chạy trên CI** (sandbox
không có PostgreSQL) — cần xem CI xanh mới tính là đã kiểm.

---

## Sau khi sửa, đường đi để thư viện rubric có nội dung

Đăng nhập `adhra@vinuni.edu.vn` (ADMIN) hoặc `hr@vinuni.edu.vn` (HR_LEAD):

1. **Vào `/rubrics`** → nay thấy 4 nút ở cột trái.
2. Chọn một trong ba đường:
   - **Tạo rubric nháp** — tự gõ từ đầu.
   - **Sinh từ JD dán tay** — dán JD, chọn nhóm, AI đề xuất bộ tiêu chí.
   - **Dùng bộ mẫu ví dụ (Backend Python)** — 1 rubric viết sẵn trong mã nguồn
     (`frontend/src/data/rubric-proposal-it-backend.json`), dùng để xem một rubric đầy đủ
     trông thế nào. **Không phải AI.**
3. Rà lại tiêu chí, cân trọng số (mỗi nhóm MUST/NICE phải cộng đúng 100).
4. **Lưu bản nháp** → trạng thái `DRAFT`.
5. **`hr@vinuni.edu.vn` (HR_LEAD) vào xuất bản.** ADMIN không xuất bản được — đây là chủ ý.
6. Rubric `PUBLISHED` mới hiện trong hộp "Dùng rubric đã xuất bản" ở trang vị trí.

Bước 5 là chỗ dễ tắc nhất khi test một mình bằng tài khoản ADMIN. Nếu muốn test trọn vòng
bằng một tài khoản, gán thêm `HR_LEAD` cho `adhra` trong **Admin → Người dùng** (chọn
nhiều vai trò được).

---

## Còn lại cho agent — chưa làm

Ba việc dưới đây **không** sửa trong lượt này vì chúng là quyết định sản phẩm, không phải
lỗi rõ ràng:

1. **Nút "Dùng bộ mẫu ví dụ" nằm lẫn giữa hai nút AI.** Nhãn không nói rõ nó không gọi
   AI. Dòng caption bên dưới có giải thích nhưng dễ bỏ qua. Đề xuất: đổi nhãn thành
   "Xem rubric mẫu có sẵn (không dùng AI)".
2. **Thư viện rỗng không phân biệt "chưa ai tạo" với "tạo rồi nhưng bị lọc".** Hiện chỉ
   một câu "Chưa có rubric nào." Đề xuất: nếu `versions.length === 0` **và** `can_create`
   thì thêm dòng hướng dẫn chọn một trong các nút bên trên.
3. **`suggestPositions` lọc mất vị trí chưa có nhóm mà không nói vì sao.** Thông báo hiện
   tại ("Chưa có vị trí nào được gán Nhóm vị trí") chỉ đúng khi thật sự không có vị trí
   nào. Nếu có 10 vị trí nhưng cả 10 chưa gán nhóm, câu đó gây hiểu sai là chưa có vị trí.
   Đề xuất: tách hai trường hợp và nêu số lượng.
