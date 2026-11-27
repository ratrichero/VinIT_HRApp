# Quy ước cho coding agent (đọc trước khi sửa bất cứ thứ gì)

Dự án có **4 agent làm song song trên 4 fork**. Tài liệu này là phần chung —
đọc hết trước khi mở editor. Kế hoạch phân công ở `doc/PLAN_4_AGENT.md`.

Ngôn ngữ: **tiếng Việt** trong trao đổi, commit message, comment và tài liệu.
Code định danh (tên hàm, biến, route) giữ tiếng Anh theo khuôn sẵn có.

---

## 1. Chạy test — đọc mục này trước, đừng đoán

| Việc | Lệnh | Ghi chú |
|---|---|---|
| Test backend | `pytest backend/tests -q` | Có thể cần `/tmp/venv/bin/pytest` nếu `pytest` hệ thống không có |
| Test frontend | `cd frontend && npm run test:unit` | Danh sách file ghi trong `package.json` |
| Test i18n riêng | `cd frontend && npm run test:i18n` | |
| E2E (cần trình duyệt) | `npm run test:e2e:<tên>` | Xem danh sách trong `package.json` |
| Kiểu | `cd frontend && npm run type-check` | |
| Lint FE | `cd frontend && npm run lint` | |
| Build | `cd frontend && npm run build` | |
| Ruff (phạm vi CI) | xem lệnh đầy đủ trong `.github/workflows/ci.yml` | Chỉ một số file, không phải toàn repo |

### 1.1. `174 skipped` nghĩa là bạn chưa dựng DB — không phải bình thường

Test tích hợp **tự skip** khi không có `TEST_DATABASE_URL`. Một dòng là đủ:

```bash
# cổng riêng cho từng agent để không đụng nhau
bash scripts/test-db.sh --port 55433 --name hra_agentx_test
export TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55433/hra_agentx_test'
pytest backend/tests -q     # kỳ vọng: 671 passed, 0 skipped
```

Chưa có PostgreSQL nào chạy trên máy? `bash scripts/local-pg.sh --port 55433 --name hra_agentx_test`
dựng luôn binary (bundle `pgserver`, không cần root), data dir, hai shim extension rồi gọi
script trên; `--stop` để tắt. Đầu file đó ghi khác biệt **PG 16.2 ở máy vs PG 17 ở CI**
(pgvector 0.6.2 vs 0.8.x) — nguyên nhân của những lần "xanh trên máy, đỏ trên CI".

Script này là **nguồn duy nhất** — CI cũng chạy đúng nó, nên máy và CI không
lệch nhau. Nó tự lo phần dễ sai: tạo role stub, `schema auth`, và **bỏ qua
`00035`** (xem mục 1.2). Đừng chép tay danh sách migration từ
`backend/tests/README.md` — danh sách đó đã lỗi thời (dừng ở `00026`).

Nếu vẫn còn `skipped` sau khi export biến: biến chưa vào đúng shell, hoặc tên DB
không kết thúc `_test` (conftest sẽ từ chối và test skip im lặng — đây là cái bẫy
đã làm 174 test không chạy suốt 11 ngày).

### 1.2. TUYỆT ĐỐI không trỏ test vào Supabase

`backend/tests/conftest.py` sẽ từ chối nếu host không phải cục bộ hoặc tên DB
không kết thúc `_test`. Đừng tìm cách lách. Lý do: fixture chạy
`TRUNCATE app_private.positions CASCADE` và `TRUNCATE auth.users CASCADE` —
**xoá gần như toàn bộ dữ liệu**.

Có đúng **một** Supabase dùng chung (`myrymlqdbyqmpynesiwk`) và chỉ người điều
phối được áp migration lên đó. Cần migration mới thì đề xuất, không tự áp.

`00035_purge_test_cv_jd_data.sql` là migration **xoá dữ liệu một lần** cho vòng
demo, không phải thay đổi lược đồ. Nó đòi schema sao lưu `app_backup_20261119`
(không migration nào tạo) nên **luôn ném lỗi trên DB trắng**. CI bỏ qua file này;
bạn cũng bỏ qua. Đừng sửa nó — nó đã áp lên Supabase thật.

---

### 1.3. Nếu repo bỗng "sạch" mà `git ls-files` chỉ ra 10 file

Đã xảy ra thật (2026-11-30). `HEAD` tụt về commit gốc `3bad733` chỉ có 10 file
`doc/`; toàn bộ code nằm trong working tree dạng untracked. Nhìn `git status` thì
giống "repo mới clone", nhưng thực ra **mất track**, không mất code.

Chẩn đoán trong 5 giây:

```bash
git ls-files | wc -l          # 10 → sai, phải là 616
git rev-parse HEAD            # 3bad733... → sai
```

Sửa — **kiểm trước khi sửa**, đừng reset mù:

```bash
# 1. working tree có khớp remote không? (dùng index tạm, không đụng index thật)
export GIT_INDEX_FILE=/tmp/idx && rm -f $GIT_INDEX_FILE
git read-tree origin/arena/ea6e2570-vinit-hrapp && git add -A .
git diff --cached --name-only origin/arena/ea6e2570-vinit-hrapp | wc -l   # 0 = khớp
rm -f $GIT_INDEX_FILE

# 2. khớp rồi thì trỏ lại, không mất gì
git reset --soft origin/arena/ea6e2570-vinit-hrapp
```

Nếu bước 1 **không** ra 0: dừng lại, có thay đổi thật cần giữ. Đừng reset.

Cùng đợt mất đó cũng mất `node_modules` và venv. Cách nhận ra: test FE báo
`Cannot find module 'typescript'`, pytest báo `No module named pytest`. Cài lại
`npm install` và `python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -e './backend[dev]'`.

---

## 2. Migration

1. **Không tự đặt số.** Xin người điều phối cấp số tiếp theo (`00042+`).
2. **Không sửa file migration đã áp.** Cần đổi thì tạo file mới.
3. Một migration làm một việc. Đừng gộp "thêm bảng" và "xoá dữ liệu" vào một file
   — chính vì gộp kiểu đó mà `00035` làm sập CI 11 ngày.
4. **Migration xoá/sửa dữ liệu phải tách riêng** và không đặt tên trong dãy lược
   đồ, để CI dựng được schema mà không cần dữ liệu.

---

## 3. Test phải kiểm ngược được

Viết test xong thì **gỡ dòng sửa ra, test phải đỏ**. Nếu vẫn xanh, test không
kiểm gì cả. Đã có 3 lần bắt được lỗi thật nhờ bước này.

Bẫy đã gặp, đừng lặp lại:

- **Đừng tìm chuỗi thô trong cả thân hàm** — nó bắt cả comment và docstring, test
  xanh dù code sai. Chỉ kiểm mã đã khai báo: cột trong `SELECT` (bỏ dòng `--`),
  SQL trong `text(...)`, hoặc danh sách `clauses`.
- **Đừng viết `text(""" ... """)` trong docstring Python** → SyntaxError.
- Test khẳng định theo **ô nhập của người dùng** sẽ đỏ ngay khi tính năng đổi
  hành vi (xem `test_position_jd_v1_...`: ô "ngôn ngữ JD" đã bị bỏ, ngôn ngữ nay
  dò từ nội dung). Kiểm **hành vi**, không kiểm đầu vào.
- Test ghi cứng số phiên bản (`version_number=1`) sẽ vi phạm `UNIQUE` khi đã có
  bản ghi trước. Dùng `MAX(...)+1` hoặc để DB cấp.

---

## 4. i18n — chỉ có MỘT file, ánh xạ Việt → Anh

**Không có `vi.json`.** Chỉ có `frontend/src/i18n/en.json`. Tiếng Việt là bản gốc
và chính là **khoá**:

```json
{ "Vị trí tuyển dụng": "Recruitment positions" }
```

`translate('Vị trí tuyển dụng', 'vi')` trả lại khoá; `'en'` trả giá trị. `translate`
còn dựng bảng nghịch để dịch ngược (Anh → Việt), nên **giá trị tiếng Anh phải
không trùng nhau** — hai khoá khác nhau cùng một bản dịch sẽ làm dịch ngược ra sai.

Quy ước khi thêm chữ mới:
- Viết nhãn bằng **tiếng Việt** trong code, bọc `t('...')`.
- Thêm một dòng vào `en.json`: khoá = đúng chuỗi tiếng Việt, giá trị = tiếng Anh.
- Dịch **thật**. `"X": "X"` làm test xanh nhưng người dùng thấy tiếng Việt trong
  giao diện tiếng Anh. Test i18n chỉ kiểm **có entry**, không kiểm bản dịch đúng.
- Chuỗi không có chữ Việt (`IN_REVIEW`, `application/pdf`, mã lỗi) **không** cần dịch.
- `npm run test:i18n` đọc cây cú pháp TSX nên nó chỉ thấy literal, không thấy chuỗi
  ghép động. Ghép chuỗi thành nhãn là cách chắc chắn làm mất bản dịch.

---

## 5. Không ghi điều chưa xảy ra

Đây là lỗi đã có thật, không phải giả định:

- Không thêm cột `sent_at` / `delivered` / `notified` khi **chưa có cơ chế gửi**.
  Đã có test khoá điều này trong `backend/tests/test_notifications.py`.
- Không ghi vào audit một giá trị mà câu `SELECT` nạp lên không có. Đúng lỗi này
  (`cv["version_number"]`) làm duyệt bộ tiêu chí thứ hai nổ 500 và không ai biết
  suốt 11 ngày.
- Nếu một hành động có thể thất bại (gửi thư, gọi API ngoài), phải **hiện lỗi ra**,
  không nuốt.

---

## 6. Ràng buộc nghiệp vụ không được tự đổi

- Ma trận trạng thái hồ sơ là cố định. Lịch phỏng vấn là **dữ liệu bổ sung**, không
  phải điều kiện để chuyển `SHORTLIST → INTERVIEW`.
- Nhiều người phỏng vấn: **OBSERVER không có phiếu chấm**, chỉ INTERVIEWER chấm.
  Người tham gia xem được mà không cần share.
- Không seed dữ liệu mẫu vào DB thật, không gửi thư cho ứng viên thật.

---

## 7. Phạm vi file

Mỗi luồng sở hữu một tập file (xem §3 của `doc/PLAN_4_AGENT.md`). Ba file **ai
cũng cần sửa**, nên quy ước:

`backend/app/api/__init__.py` · `frontend/src/types/index.ts` · `frontend/src/i18n/en.json`

→ Sửa **sau cùng trong ngày**, **commit riêng**, **nhỏ nhất có thể**. Đừng gộp
vào commit tính năng.

---

## 8. Commit

- Nêu **lý do**, không chỉ việc đã làm. Người đọc sau cần biết vì sao.
- Dùng `git commit -F -` với heredoc; `git commit -m` nuốt dấu backtick.
- Chạy test **trước** khi commit và ghi kết quả vào commit message.
- **CI đỏ thì không xin gộp.** CI đã từng đỏ 11 ngày liên tục mà vẫn có 8 commit
  được push — đừng để lặp lại.

---

## 9. Quy trình gộp

Làm trên fork của mình → CI trên fork xanh → người điều phối **cherry-pick một
commit** vào nhánh chính. Không merge cả nhánh, giữ lịch sử tuyến tính.
