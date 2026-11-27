/**
 * Thứ tự ba khối trong trang thư viện rubric.
 *
 * Vì sao khoá: bố cục này đã bị đảo hai lần rồi. Lần đầu là hai cột (nút +
 * danh sách bên trái, chi tiết bên phải) làm mỗi cột tiêu chí chỉ còn ~330px.
 * Lần này yêu cầu là đẩy khối chi tiết XUỐNG DƯỚI cùng, các nút lên trên.
 *
 * Thứ tự đúng:
 *   1. Tạo rubric mới      — việc đầu tiên HR làm mỗi lần mở thư viện
 *   2. Rubric trong thư viện — chọn cái đang có
 *   3. Chi tiết rubric      — chỉ hiện sau khi đã chọn hoặc đang soạn
 *
 * Kiểm bằng thứ tự xuất hiện trong mã nguồn, vì đây là component client
 * ('use client') — HTML trả về từ máy chủ không chứa các khối này.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const PAGE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'app', 'rubrics', 'page.tsx'),
  'utf8',
);

const indexOf = (needle) => {
  const at = PAGE.indexOf(needle);
  assert.notStrictEqual(at, -1, `không tìm thấy "${needle}" trong page.tsx`);
  return at;
};

test('các nút tạo nằm ở khối trên cùng', () => {
  const buttons = indexOf("t('Tạo rubric mới')");
  const list = indexOf("t('Rubric trong thư viện')");
  const detail = indexOf("t('Chi tiết rubric')");
  assert.ok(buttons < list, 'khối nút phải đứng trước danh sách rubric');
  assert.ok(list < detail, 'danh sách rubric phải đứng trước khối chi tiết');
});

test('khối chi tiết không còn nằm cạnh danh sách', () => {
  // Bố cục cũ: Stack direction row + Card cột trái cố định 360px.
  assert.ok(!PAGE.includes('lg: 360'), 'vẫn còn cột trái cứng 360px của bố cục cũ');
  // Ba khối xếp dọc, không phải hai cột.
  const stackStart = PAGE.indexOf('        {/* ── KHỐI 1');
  assert.notStrictEqual(stackStart, -1);
  const wrapper = PAGE.slice(stackStart - 200, stackStart);
  assert.ok(!wrapper.includes("direction={{ xs: 'column', lg: 'row' }}"),
    'khối bọc vẫn là 2 cột — cần xếp dọc');
});

test('danh sách rubric chỉ render một lần', () => {
  // Render hai lần (một ở cột trái, một chỗ khác) là cách chắc chắn nhất để
  // hai bản lệch nhau sau vài lần sửa.
  const occurrences = (PAGE.match(/versions\.map\(/g) || []).length;
  assert.strictEqual(occurrences, 1, `versions.map xuất hiện ${occurrences} lần`);
});

test('nút xuất bản chỉ có một chỗ, nằm trong khối chi tiết', () => {
  const count = (PAGE.match(/t\('Xuất bản rubric'\)/g) || []).length;
  assert.strictEqual(count, 1, 'nút xuất bản bị lặp');
  const publish = indexOf("t('Xuất bản rubric')");
  const detail = indexOf("t('Chi tiết rubric')");
  assert.ok(publish > detail, 'nút xuất bản phải nằm trong khối chi tiết');
});

test('khối chi tiết chỉ hiện khi đang soạn hoặc đã chọn', () => {
  assert.ok(
    PAGE.includes('{(creating || selected) && ('),
    'khối chi tiết phải có điều kiện, nếu không sẽ chiếm chỗ khi chưa chọn gì',
  );
});
