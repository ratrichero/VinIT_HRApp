/**
 * "Lấy JD từ vị trí khác" — ba điều người dùng đã chốt, khoá ở đây.
 *
 * 1. Sao chép vào ô soạn thảo, KHÔNG lưu thẳng và KHÔNG chuyển hẳn.
 * 2. Chỉ cùng Nhóm vị trí.
 * 3. Chỉ cần quyền trên vị trí đích.
 *
 * Test này kiểm phía giao diện. Phía máy chủ có
 * `backend/tests/test_jd_template_from_position.py` chạy trên PostgreSQL thật.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const PAGE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'app', 'positions', '[id]', 'page.tsx'),
  'utf8',
);
const API = fs.readFileSync(path.join(__dirname, '..', 'src', 'lib', 'api.ts'), 'utf8');

test('giao diện KHÔNG tự lưu khi lấy JD — chỉ đổ vào ô soạn thảo', () => {
  // Nếu lấy xong mà tự gọi createJdVersion thì JD của vị trí khác (còn tên vị
  // trí cũ, số lượng cũ) thành phiên bản chính thức mà không ai đọc lại.
  const body = PAGE.slice(
    PAGE.indexOf('const loadJdFromPosition'),
    PAGE.indexOf('const saveJd'),
  );
  assert.ok(body.includes('setJdContent(data.content_text)'), 'phải đổ vào ô soạn thảo');
  assert.ok(!body.includes('createJdVersion'), 'không được tự lưu');
  assert.ok(!body.includes('savingJd'), 'không được đi qua đường lưu');
});

test('ghi đè nội dung đang soạn phải hỏi trước', () => {
  // Ô JD là chỗ HR có thể đã gõ vài trăm chữ; thao tác này không lùi được.
  assert.ok(PAGE.includes('jdDirty && !window.confirm'), 'thiếu bước xác nhận ghi đè');
});

test('chỉ liệt kê vị trí cùng Nhóm vị trí', () => {
  assert.ok(PAGE.includes('p.job_family_id === position.job_family_id'),
    'không lọc theo nhóm — HR sẽ thấy cả vị trí khác nhóm rồi bị 404');
  assert.ok(PAGE.includes("p.position_id !== positionId"), 'vẫn liệt kê chính vị trí này');
});

test('khối chọn nguồn ẩn khi vị trí chưa có Nhóm vị trí', () => {
  // Chưa có nhóm thì không có gì để đối chiếu, và máy chủ cũng từ chối.
  assert.ok(PAGE.includes('position.job_family_id && jdSourceOptions.length > 0'),
    'khối chọn nguồn hiện cả khi không thể dùng');
});

test('nhắc HR sửa lại nội dung sau khi sao chép', () => {
  assert.ok(PAGE.includes('Sửa lại tên vị trí, số lượng và địa điểm trước khi lưu.'),
    'thiếu lời nhắc — đây là lý do phải sao chép chứ không lưu thẳng');
});

test('API client gọi đúng endpoint và đúng kiểu dữ liệu', () => {
  assert.ok(API.includes('/jd-template'), 'thiếu endpoint getJdTemplate');
  assert.ok(API.includes('source_position_id: sourcePositionId'), 'sai tham số gửi lên');
});
