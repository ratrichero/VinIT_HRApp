# Audit các nâng cấp gần đây — 2026-11-27

**Phạm vi.** Ba commit mới nhất của arena (`fb57966`, `8f0dba2`, `772e78c` — sửa lỗi 422
`requirement_spec`, nhận diện bằng cấp, thêm `preview-spec`), 46 commit đã đồng bộ trước
đó (lịch phỏng vấn, chuông thông báo, `InterviewPanel`), và ba commit của ta
(`df9a63c`, `06b0a4c`, `d2b652a`).

**Phương pháp.** Đọc diff từng file; chạy `tsc`, `test:unit` (211), `test:i18n` (3),
`next build` — tất cả xanh sau merge. Chuỗi lỗi ở mục 2 được chứng minh bằng script
Python chạy trên venv thật (`/tmp/venv`), không phải suy luận từ mã.

---

## 1. [CAO] `GET /interviews` không có bộ lọc nào → lộ lịch phỏng vấn toàn hệ thống

`backend/app/api/interviews.py:301-352`.

`list_interviews` chỉ chạy `_require_active` (tài khoản còn hoạt động), rồi dựng
`clauses = ["1=1"]`. Kiểm tra quyền **chỉ nằm trong nhánh `if position_id:`** và nhánh
`mine=true`:

```python
clauses = ["1=1"]
if position_id:
    allowed = ...            # chỉ chạy khi có position_id
    if not allowed: raise HTTPException(403, ...)
if mine:
    clauses.append(...)      # chỉ khi mine=true
```

Nghĩa là bất kỳ ai có tài khoản đang hoạt động — người phỏng vấn, OBSERVER, hiring
manager — gọi `GET /api/v1/interviews` **không tham số** sẽ nhận tới 200 buổi của
**mọi** vị trí, kèm `candidate_name`, `position_code`, `position_title`
(`_INTERVIEW_SELECT` join `application_identities`).

Docstring của chính hàm nói ngược lại: "Không có `mine` thì phải là HR của vị trí (hoặc
HR_LEAD/ADMIN) mới xem được lịch của vị trí đó". Không có test nào khoá trường hợp này
(`grep` trong `tests/test_interviews.py` không có test list không tham số).

Đối chiếu: `get_interview` (một buổi) **có** kiểm tra (`is_hr or is_participant` → 403),
và `list_notifications` lọc đúng `user_id = :actor`. Đây là chỗ duy nhất lệch.

**Đề xuất.** Khi không có `position_id` và không `mine`, hoặc yêu cầu HR_LEAD/ADMIN, hoặc
lọc theo các vị trí người đó phụ trách; chặt hơn nữa là bắt buộc một trong hai tham số.
Kèm test: người phỏng vấn gọi list không tham số phải nhận 403.

## 2. [CAO] Tiêu chí "bằng cấp" không nêu bậc → chấm điểm theo bậc đại học, ngầm

Ba chỗ của cùng một lỗi.

**(a) Máy suy ra DEGREE nhưng không có ngưỡng.** `deterministic_matching.py:689-693`
chỉ gán `required_degree = None` — một câu lệnh **không làm gì** (dead code). Ý đồ đúng
(để trống), nhưng bước sau không xử lý được trường hợp trống.

**(b) API bỏ spec đó khỏi phản hồi.** `criteria.py:67-85`, `_schema_safe_spec` gọi
`RequirementSpec.model_validate(spec)`; schema (cố ý, theo audit M1) từ chối DEGREE
thiếu `required_degree_level`, nên spec bị thay bằng `None`. Đo thật:

```
1) spec máy suy ra          : DEGREE level= None
   [warning] requirement_spec omitted from response: failed schema validation kind=DEGREE
2) _schema_safe_spec trả về : None
```

Hệ quả trên giao diện: HR thấy "Kỹ năng hoặc công nghệ" (fallback của `specKindOf(null)`)
và **không bao giờ thấy ô "Bậc bằng tối thiểu"** mà commit `8f0dba2` nói là đã có.

**(c) Chấm điểm đoán bậc 3.** `_evaluate_degree` (`deterministic_matching.py:1162`):

```python
required = spec.required_degree_level or 3
```

Dù giao diện ghi "Để trống thì tiêu chí chỉ dò từ khoá" (`RubricItemEditor.tsx`), máy
chấm như thể yêu cầu **đại học**. Một ngưỡng chưa ai duyệt đi thẳng vào điểm — đúng
điều commit `8f0dba2` tuyên bố là không làm.

**Hệ quả kèm theo.** Khi HR mở rubric/vị trí có tiêu chí đó rồi bấm Lưu, `buildSpec(null,
keywords, name)` trả `{kind:'SKILL', terms:[...]}` → spec DEGREE trong DB bị **ghi đè
thành SKILL** mà không ai được hỏi.

**Đề xuất.** Chọn một trong hai: (i) cho schema nhận DEGREE với level `None` (HR điền
sau; giao diện đã có ô), hoặc (ii) giữ schema chặt và cho `build_requirement_spec` trả
`kind='SKILL'` kèm cờ "cần xem lại" thay vì trả DEGREE thiếu ngưỡng. Cả hai đường đều
phải sửa `required_degree_level or 3` — không được đoán ngưỡng.

## 3. [TRUNG BÌNH] Mỗi lần mở/đổi hồ sơ tốn thêm một request tải **toàn bộ** lịch phỏng vấn

`frontend/src/components/positions/InterviewPanel.tsx:105`: `interviewsApi.list({})` —
không truyền `position_id`, rồi lọc ở client (`items.filter(item => item.application_id
=== applicationId)`). Backend trả tới 200 dòng, mỗi dòng có ba subquery đếm.

Đo được trong log của `profile-transition-requests.e2e.cjs` (sau merge): mỗi lần bấm `n`
phát sinh `{"/v1/interviews": 1, "/v1/applications/app-X": 1}` — tức **2 GET** cho một
lần đổi hồ sơ, trước đây là 1. Đây là hồi quy đúng vào thứ cả dự án đang giảm.

**Đề xuất.** Truyền `position_id` (đã có trong URL), hoặc tốt hơn: endpoint theo
`application_id`.

## 4. [THẤP] `missingThreshold` ở trang rubrics lệch với `specProblem` dùng chung

`frontend/src/app/rubrics/page.tsx:236-245` kiểm LANGUAGE chỉ với `required_languages`
và `required_ielts`; bỏ qua `required_toeic`, `required_cefr`, `required_language_rank`
— trong khi `specProblem` (`requirementSpec.ts`) kiểm đủ cả bốn. Kết quả: tiêu chí
LANGUAGE do AI sinh ra với `required_cefr='B2'` bị **chặn lưu** kèm câu sai ("chưa nêu
ngôn ngữ nào, cũng chưa có mức IELTS tối thiểu").

Đúng loại lỗi mà việc tách `requirementSpec.ts` sinh ra để dẹp — nhưng trang rubrics vẫn
giữ bản sao thứ hai.

**Đề xuất.** Thay `missingThreshold()` bằng `specProblem()` từ module chung.

## 5. [THẤP] `changeKind` chép lại logic của `withKind`

`RubricItemEditor.tsx` (hàm `changeKind`) lặp lại từng dòng xoá ngưỡng mà `withKind` đã
làm. Hai bản sao của cùng một luật → nguy cơ lệch y như lần trước (sửa trang rubrics
rồi, trang vị trí vẫn 422).

**Đề xuất.** Gọi `withKind(spec, next)` rồi mới `onChange`.

## 6. [THẤP] Nháp cũ mất phần `specs` khi khôi phục

`rubrics/page.tsx` bỏ state `specs` khi bỏ ô JSON. `currentDraft()` không còn ghi
`specs`, `applySnapshot()` không còn đọc `specs`. Nháp tạo trước nâng cấp (còn trong
`localStorage`) sẽ được khôi phục mà **mất các sửa `requirement_spec` HR đã gõ trong ô
JSON**. Mức độ: thấp (nháp là tạm, và trang dọn nháp sau khi lưu thành công).

**Đề xuất.** Tăng phiên bản khoá nháp (`rubricDraftKey`) để nháp cũ bị bỏ có ý, thay vì
khôi phục thiếu.

## 7. [THÔNG TIN] Dead code

`deterministic_matching.py:692-693` — `if kind == "DEGREE" and required_degree is None:
required_degree = None`. Không có tác dụng; nên xoá hoặc thay bằng xử lý thật (mục 2).

---

## Đã kiểm và **không** thấy lỗi

- **Handler 422 ở `main.py` trả câu của validator**: đã grep toàn bộ `raise ValueError`
  trong `app/schemas/` — mọi câu đều là chuỗi tĩnh, không nội suy dữ liệu người dùng, nên
  không rò mật khẩu/token như comment cạnh đó cảnh báo. Lưu ý nhỏ: khi request có cả lỗi
  `value_error` lẫn lỗi kiểu, người dùng chỉ thấy câu của `value_error` trước.
- **`GET /notifications`**: lọc đúng `user_id = :actor`.
- **`GET /interviews/{id}`**: có kiểm tra HR hoặc người tham gia.
- **`preview-spec`**: không đọc/ghi DB, chỉ chạy hàm suy luận; không rò dữ liệu.
- **`buildSpec` luôn kèm `terms`**: đã đọc, không còn đường gửi SKILL rỗng.
- **Sau merge**: `tsc` sạch, `test:unit` 211 pass/0 fail, `test:i18n` 3 pass,
  `next build` exit 0.

## Chưa kiểm

- **Không chạy được test backend cần DB**: máy này không có PostgreSQL (`initdb`/`pg_ctl`
  không có), nên bốn file `tests/test_interviews*.py` và toàn bộ 716 test backend chưa
  chạy. Kết luận ở mục 1-2 là đọc mã + chạy script Python thật trên venv, **không** qua DB.
- Chưa chạy lại toàn bộ e2e sau merge (chỉ `test:unit`, `test:i18n`, `tsc`, `build`).
- Chưa nhìn tận mắt giao diện rubrics mới (đã bỏ ô JSON) — chỉ đọc mã.
