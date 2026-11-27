/**
 * Bố cục tab Tiêu chí ở trang chi tiết vị trí.
 *
 * Sáu thay đổi theo yêu cầu người dùng, mỗi cái khoá một dòng ở đây. Lý do phải
 * khoá: đây là những thứ dễ bị thêm lại khi ai đó "bổ sung cho đầy đủ" — và
 * người dùng đã phải chỉ ra chúng nhiều lần.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const PAGE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'app', 'positions', '[id]', 'page.tsx'),
  'utf8',
);

test('không hiện UUID nguồn phiên bản rubric', () => {
  // "Nguồn phiên bản rubric: 378731c5-eb18-…" là id kỹ thuật, HR không dùng
  // được vào việc gì. Nếu cần tra nguồn gốc thì tra trong lịch sử duyệt.
  assert.ok(!PAGE.includes('source_template_version_id && <Alert'),
    'vẫn hiện UUID nguồn rubric');
});

test('không còn alert "Đang là bản nháp…" dài dòng', () => {
  assert.ok(!PAGE.includes('Đang là bản nháp. Nếu muốn dùng rubric mẫu'),
    'chuỗi hướng dẫn dài vẫn còn');
  // Nút huỷ phải chuyển vào khối gộp, không biến mất.
  assert.ok(PAGE.includes('setDiscardDraftOpen(true)'), 'mất luôn lối huỷ bản nháp');
  assert.ok(PAGE.includes("t(\"Huỷ bản nháp\")"), 'nút huỷ chưa vào khối gộp');
});

test('mỗi nhóm chỉ một dòng tiêu đề, không lặp "Tiêu chí bắt buộc"', () => {
  // Trước: chip "BẮT BUỘC" + chữ "Tiêu chí bắt buộc (70% tổng điểm)".
  // Nay: chip "BẮT BUỘC" + "(70% tổng điểm)".
  assert.ok(!PAGE.includes('Tiêu chí bắt buộc ('), 'còn chữ "Tiêu chí bắt buộc ("');
  assert.ok(!PAGE.includes('Tiêu chí ưu tiên ('), 'còn chữ "Tiêu chí ưu tiên ("');
  assert.ok(PAGE.includes('${t("tổng điểm")}'), 'mất phần trăm tổng điểm');
});

test('bỏ dòng "Tổng trong nhóm" ở đáy mỗi cột', () => {
  // Tổng đã hiện ở đầu cột và ở cảnh báo khi sai; dòng thứ ba ở đáy là thừa.
  const inColumn = (PAGE.match(/Tổng trong nhóm:/g) || []).length;
  // Còn lại duy nhất một chỗ: hộp thoại điều chỉnh trọng số (nơi cần con số
  // khi đang sửa từng tiêu chí).
  assert.ok(inColumn <= 1, `còn ${inColumn} chỗ "Tổng trong nhóm"`);
});

test('không nhắc cùng một việc hai lần ở hai khối', () => {
  // Khi bộ tiêu chí chưa duyệt, khối duyệt đã nêu trạng thái + nút bấm, nên
  // "Hành động tiếp theo" ở khối tổng quan phải ẩn đi.
  assert.ok(PAGE.includes('criteriaAwaitingApproval'), 'thiếu cờ ẩn khối trùng');
  assert.ok(PAGE.includes('!criteriaAwaitingApproval && <NextActionCard'),
    'NextActionCard vẫn hiện cả khi khối duyệt đã nhắc');
});

test('tiêu đề trạng thái gọn, không kèm câu mô tả quy trình chung', () => {
  assert.ok(!PAGE.includes('Sau khi HR duyệt, hệ thống sẽ chuyển sang bước phê duyệt'),
    'còn câu mô tả quy trình lặp lại');
  assert.ok(!PAGE.includes('Sau khi HM duyệt, bộ tiêu chí sẽ được khóa và dùng để đánh giá'),
    'còn câu mô tả quy trình lặp lại');
});

test('HR không thấy mã kỹ thuật trong phần tóm tắt đặc tả', () => {
  // Dòng tóm tắt từng mở đầu bằng `SKILL`/`YEARS`, đúng thứ vừa bị bỏ khỏi ô nhập.
  assert.ok(!PAGE.includes('const details: string[] = [spec.kind]'),
    'tóm tắt vẫn ghép mã kind thô');
  assert.ok(PAGE.includes('KIND_LABEL[specKindOf(spec)]'), 'phải dùng nhãn tiếng Việt');
});

test('ô nhập dùng cùng từ ngữ với trang thư viện rubric', () => {
  // Hai trang cùng gửi một schema; dùng hai bộ nhãn khác nhau cho cùng một khái
  // niệm là cách chắc chắn nhất khiến HR tưởng chúng là hai thứ khác nhau.
  assert.ok(PAGE.includes('Cách máy so khớp'), 'thiếu nhãn chung cho ô chọn loại');
  assert.ok(!PAGE.includes('Thuật ngữ bằng chứng (phân tách bằng dấu phẩy)'),
    'còn nhãn dài cũ');
  assert.ok(!PAGE.includes('Ngôn ngữ (phân tách bằng dấu phẩy)'), 'còn nhãn dài cũ');
});
