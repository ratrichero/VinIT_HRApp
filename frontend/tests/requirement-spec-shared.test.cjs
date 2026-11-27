/**
 * Hai trang soạn tiêu chí phải dùng CHUNG một logic `requirement_spec`.
 *
 * Lỗi có thật đã xảy ra: sửa trang thư viện rubric xong, trang chi tiết vị trí
 * vẫn 422 vì nó vẫn gửi `requirement_spec` thô từ state. Chép logic hai nơi thì
 * lần sau lại lệch, và lần này người dùng phát hiện trước mình.
 *
 * Test này không kiểm nội dung hàm (đã có rubric-build-spec.test.cjs) — nó kiểm
 * *cấu trúc*: cả hai trang có đi qua `@/lib/requirementSpec` hay không.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (...parts) => fs.readFileSync(path.join(__dirname, '..', ...parts), 'utf8');
const RUBRICS = read('src', 'app', 'rubrics', 'page.tsx');
const POSITION = read('src', 'app', 'positions', '[id]', 'page.tsx');
const EDITOR = read('src', 'components', 'positions', 'RubricItemEditor.tsx');

test('cả hai trang đều import module chung', () => {
  for (const [label, src] of [['rubric', RUBRICS], ['vị trí', POSITION]]) {
    assert.ok(src.includes("@/lib/requirementSpec"), `trang ${label} không dùng module chung`);
  }
});

test('không trang nào tự định nghĩa lại danh sách loại tiêu chí', () => {
  // Hai bản định nghĩa là hai chỗ phải sửa mỗi lần thêm loại mới.
  for (const [label, src] of [['rubric', RUBRICS], ['vị trí', POSITION], ['editor', EDITOR]]) {
    const inline = src.match(/\['SKILL',\s*'YEARS',\s*'DEGREE'/g) || [];
    assert.strictEqual(inline.length, 0, `${label} tự khai báo lại SPEC_KINDS`);
  }
});

test('trang vị trí dựng spec trước khi gửi, không gửi state thô', () => {
  // Trước đây: requirement_spec: editingCriterion.requirement_spec || null
  assert.ok(!POSITION.includes('requirement_spec: editingCriterion.requirement_spec || null'),
    'vẫn gửi spec thô từ state');
  assert.ok(POSITION.includes('buildSpec(editingCriterion.requirement_spec'),
    'phải dựng spec qua hàm chung');
  assert.ok(POSITION.includes('specProblem(spec)'), 'phải kiểm thiếu ngưỡng trước khi gửi');
});

test('trang vị trí hiện nhãn người đọc được, không hiện mã kỹ thuật', () => {
  // Ô chọn loại từng có 5 <MenuItem> cứng: Kỹ năng / Số năm kinh nghiệm / …
  // Nay lấy từ KIND_LABEL để hai trang dùng đúng một bộ nhãn.
  assert.ok(!POSITION.includes('<MenuItem value="CERTIFICATION">{t("Chứng chỉ")}</MenuItem>'),
    'vẫn còn danh sách MenuItem cứng');
  assert.ok(POSITION.includes('SPEC_KINDS.map(k =>'), 'phải render từ SPEC_KINDS');
  assert.ok(POSITION.includes('KIND_LABEL[k]'), 'phải dùng nhãn chung');
});
