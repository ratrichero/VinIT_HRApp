/**
 * Cờ "chưa có ngưỡng" phải TẮT được khi HR đã điền ngưỡng.
 *
 * Lỗi có thật: máy chủ điền tạm một giá trị để response serialize được và bật
 * `threshold_pending`. Giao diện hiện cảnh báo và chặn lưu — đúng. Nhưng cờ đó
 * chỉ được máy chủ tính lại khi tải lại trang; sửa spec trong form không đụng
 * tới nó. Nên HR chọn bậc bằng xong vẫn bị chặn với câu "chưa có ngưỡng", và
 * tải lại thì máy chủ vẫn đọc ngưỡng cũ trong DB nên vẫn đánh cờ: ngõ cụt.
 *
 * Test này kiểm hai điều, bằng mã đã khai báo chứ không phải chú thích:
 *  1. `pendingAfterEdit` tồn tại và xét đúng hai loại có ngưỡng bắt buộc;
 *  2. ba đường sửa spec trong editor đều truyền cờ đã tính lại, không giữ
 *     nguyên giá trị cũ trong state.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (...parts) => fs.readFileSync(path.join(__dirname, '..', ...parts), 'utf8');
const MODULE = read('src', 'lib', 'requirementSpec.ts');
const EDITOR = read('src', 'components', 'positions', 'RubricItemEditor.tsx');
const RUBRICS = read('src', 'app', 'rubrics', 'page.tsx');

/** Cắt đúng thân một hàm khai báo, bỏ qua chú thích phía trên. */
const bodyOf = (source, marker, stopMarker) => {
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `không tìm thấy ${marker}`);
  const end = source.indexOf(stopMarker, start);
  assert.ok(end > start, `không tìm thấy điểm kết thúc ${stopMarker} của ${marker}`);
  return source.slice(start, end);
};

test('pendingAfterEdit xét đúng YEARS và DEGREE, không loại nào khác', () => {
  const body = bodyOf(MODULE, 'export function pendingAfterEdit', '\n}');
  // Hai ngưỡng bắt buộc — đúng danh sách `_PENDING_FILL` của máy chủ.
  assert.ok(/if \(kind === 'YEARS'\) return !has\(s\.min_years\)/.test(body),
    'pendingAfterEdit không xét số năm tối thiểu');
  assert.ok(/if \(kind === 'DEGREE'\) return !has\(s\.required_degree_level\)/.test(body),
    'pendingAfterEdit không xét bậc bằng tối thiểu');
  assert.ok(/return false;/.test(body), 'loại khác phải trả false, nếu không cảnh báo hiện sai');
});

test('patchSpec tính lại cờ thay vì giữ giá trị cũ trong state', () => {
  const body = bodyOf(EDITOR, 'const patchSpec =', '\n  };');
  assert.ok(body.includes('pendingAfterEdit('), 'patchSpec không tính lại cờ');
  assert.ok(/threshold_pending:\s*pendingAfterEdit\(/.test(body),
    'patchSpec không truyền threshold_pending đã tính lại — HR điền ngưỡng xong vẫn bị chặn lưu');
});

test('đổi loại tiêu chí và suy lại cũng tính lại cờ', () => {
  const changeKind = bodyOf(EDITOR, 'const changeKind = async', '\n    if (needsThreshold)');
  assert.ok(/threshold_pending:\s*pendingAfterEdit\(base\)/.test(changeKind),
    'changeKind không tính lại cờ sau khi đổi loại');
  const resync = bodyOf(EDITOR, 'const resync = async', '\n    } catch');
  assert.ok(/threshold_pending:\s*pendingAfterEdit\(next\)/.test(resync),
    'resync không tính lại cờ sau khi máy suy ra ngưỡng');
});

test('trang rubric vẫn chặn lưu khi cờ còn bật', () => {
  // Chốt chặn phía máy chủ vẫn cần: item chưa ai sửa thì cờ vẫn đúng.
  assert.ok(RUBRICS.includes('items[i].threshold_pending'),
    'trang rubric bỏ chốt chặn threshold_pending');
});
