/**
 * Trường "requirement_spec" không được bắt HR gõ JSON.
 *
 * Bối cảnh: form cũ có ô `Requirement spec (JSON)` và ô `Hướng dẫn bằng chứng`
 * bày ngang hàng với tên/mô tả. Không ai giải thích được cho HR hiểu vì sao họ
 * phải viết `{"kind":"SKILL","terms":["Python"]}` trong khi backend đã tự suy ra
 * đúng thứ đó từ tên + mô tả + từ khoá (xem `deterministic_matcher.
 * build_requirement_spec`). Tệ hơn: `JSON.parse` trần nghĩa là gõ sai một dấu
 * phẩy thì không lưu được rubric.
 *
 * Nay chỉ còn MỘT thứ HR chọn trong spec: `kind`, qua ô chọn có nhãn tiếng Việt.
 * Các trường còn lại giữ nguyên giá trị đã có — quan trọng, vì xoá `terms` của
 * một spec do AI sinh sẽ làm hỏng cách chấm điểm.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (...parts) =>
  fs.readFileSync(path.join(__dirname, '..', ...parts), 'utf8');

/** Bỏ chú thích trước khi kiểm: chính chú thích trong file có nhắc tới ô JSON
 *  cũ để giải thích vì sao bỏ. Kiểm mã thật, không kiểm lời kể về mã. */
const stripComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const EDITOR = stripComments(read('src', 'components', 'positions', 'RubricItemEditor.tsx'));
const PAGE = stripComments(read('src', 'app', 'rubrics', 'page.tsx'));

test('không còn ô nhập JSON cho HR', () => {
  assert.ok(!EDITOR.includes('Requirement spec (JSON)'), 'ô JSON vẫn còn trong trình sửa tiêu chí');
  assert.ok(!/value=\{spec\}/.test(EDITOR), 'vẫn còn ô nhập nhận chuỗi spec');
  assert.ok(!PAGE.includes('optionalRequirementSpec'), 'trang vẫn dựng spec từ chuỗi JSON');
});

test('HR chọn loại tiêu chí bằng nhãn đọc được, không phải mã kỹ thuật', () => {
  // Năm loại khớp đúng `kind` của RequirementSpec bên backend.
  for (const kind of ['SKILL', 'YEARS', 'DEGREE', 'CERTIFICATION', 'LANGUAGE']) {
    assert.ok(EDITOR.includes(`  ${kind}:`), `thiếu loại ${kind} trong KIND_LABEL`);
  }
  // Nhãn hiện ra là tiếng Việt; mã SKILL/YEARS chỉ nằm trong value của MenuItem.
  assert.ok(EDITOR.includes("SKILL: 'Kỹ năng hoặc công nghệ'"));
  assert.ok(EDITOR.includes("SKILL: 'Kỹ năng hoặc công nghệ'"), 'nhãn phải là chữ, không phải mã');
  assert.ok(!/label=\{[^}]*\bkind\b[^}]*\}/.test(EDITOR), 'không được lấy thẳng mã kind làm nhãn');
});

test('đổi loại tiêu chí giữ nguyên phần còn lại của spec', () => {
  // Nếu ghi đè cả object, một tiêu chí "3 năm Python" do AI sinh sẽ mất
  // `min_years` và `terms` ngay khi HR đổi loại — điểm chấm sẽ sai âm thầm.
  assert.ok(
    EDITOR.includes('{ ...base, kind: next }'),
    'phải trải object cũ rồi mới ghi đè kind',
  );
});

test('spec hỏng không làm trắng form', () => {
  // spec có thể là null, chuỗi, hoặc object thiếu kind — hàm đọc phải chịu được.
  assert.ok(EDITOR.includes('function specKindOf'), 'thiếu hàm đọc kind an toàn');
  assert.ok(EDITOR.includes("typeof spec?.kind === 'string'"), 'không kiểm kiểu trước khi đọc kind');
});

test('"Phân tách bằng dấu phẩy" nằm trong tooltip, không chiếm chỗ dưới ô nhập', () => {
  assert.ok(!EDITOR.includes("helperText={t('Phân tách bằng dấu phẩy')}"),
    'gợi ý vẫn hiện thường trực dưới ô nhập');
  assert.ok(EDITOR.includes('<Tooltip'), 'phải có tooltip thay thế');
  assert.ok(EDITOR.includes('Cách nhau bằng dấu phẩy'), 'nội dung hướng dẫn bị mất hẳn');
});

test('từ khoá đã tách được hiện lại thành chip', () => {
  // Gõ "Python,, FastAPI ," phải thấy máy hiểu thành hai từ, không phải đoán.
  assert.ok(EDITOR.includes('keywordList.map'), 'thiếu phần hiện lại từ khoá đã tách');
});

test('hướng dẫn bằng chứng bị thu vào khối nâng cao, đóng sẵn', () => {
  assert.ok(EDITOR.includes('<Collapse in={advanced}>'), 'thiếu khối thu gọn');
  assert.ok(EDITOR.includes('useState(false)'), 'khối nâng cao phải đóng sẵn');
  assert.ok(EDITOR.includes('Tuỳ chọn nâng cao'), 'thiếu nút mở khối nâng cao');
});

test('gợi ý dài không còn chen giữa các ô', () => {
  // Gợi ý từng nằm ngay dưới ô nhập làm các ô lệch hàng nhau. Nay chỉ còn
  // gợi ý ngắn, một dòng, ở đúng hai ô cần giải thích.
  const helperTexts = (EDITOR.match(/helperText=/g) || []).length;
  assert.ok(helperTexts <= 4, `còn ${helperTexts} chỗ helperText — quá nhiều, sẽ lệch hàng`);
});
