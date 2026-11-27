/**
 * Ba lỗi mức thấp của audit 2026-11-27, cùng một gốc: **logic bị chép tay**.
 *
 * Trước đó mỗi trang tự viết một bản kiểm "thiếu ngưỡng" và một bản `withKind`.
 * Bản chép ở `rubrics/page.tsx` lệch với `specProblem` dùng chung: nhánh
 * LANGUAGE chỉ kiểm `required_languages` + IELTS, bỏ TOEIC/CEFR/rank — nên một
 * tiêu chí ngoại ngữ chỉ có TOEIC 600 bị **chặn lưu oan**, kèm câu thông báo
 * nói sai về điều đang thiếu.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (...p) => fs.readFileSync(path.join(__dirname, '..', ...p), 'utf8');
const RUBRICS = read('src', 'app', 'rubrics', 'page.tsx');
const EDITOR = read('src', 'components', 'positions', 'RubricItemEditor.tsx');
const MODULE = read('src', 'lib', 'requirementSpec.ts');
const DRAFTS = read('src', 'lib', 'localDrafts.ts');

test('kiểm "thiếu ngưỡng" dùng specProblem chung, không chép tay', () => {
  assert.ok(RUBRICS.includes('specProblem('), 'trang rubric không dùng specProblem');
  // Bản chép tay cũ có đúng những dòng này — sự tồn tại của chúng là dấu hiệu lệch.
  assert.ok(!RUBRICS.includes("const hasLanguage = Array.isArray(spec?.required_languages)"),
    'vẫn còn bản kiểm LANGUAGE chép tay');
  assert.ok(!RUBRICS.includes("kind === 'YEARS' && spec?.min_years == null"),
    'vẫn còn bản kiểm YEARS chép tay');
});

test('specProblem thật sự nhận TOEIC/CEFR/rank cho tiêu chí ngoại ngữ', () => {
  // Đây chính là thứ bản chép tay bỏ sót.
  for (const field of ['required_toeic', 'required_cefr', 'required_language_rank']) {
    assert.ok(MODULE.includes(field), `specProblem không xét ${field}`);
  }
});

test('changeKind dùng withKind chung thay vì chép logic', () => {
  assert.ok(EDITOR.includes('withKind('), 'editor không dùng withKind');
  assert.ok(!EDITOR.includes("if (next !== 'YEARS') base.min_years = null"),
    'vẫn còn bản withKind chép tay trong editor');
});

test('nháp rubric tăng phiên bản khoá để không đọc sai nháp cũ', () => {
  // Nháp v1 lưu trường `specs`; code nay không còn đọc nó. Khôi phục nháp v1 vào
  // code mới sẽ ra rubric mất spec → DEGREE thành SKILL. Bỏ nháp cũ tốt hơn.
  assert.ok(DRAFTS.includes('rubric:pending:v2'), 'chưa tăng phiên bản khoá nháp');
  // Nhưng vẫn phải dọn được nháp v1 cũ, nếu không chúng nằm lại trong máy mãi.
  assert.ok(DRAFTS.includes('purgeDrafts(`${DRAFT_PREFIX}rubric:`'),
    'purge phải theo tiền tố chung để dọn được cả v1');
});

test('tiêu chí thiếu ngưỡng được máy chủ đánh cờ, giao diện đọc cờ đó', () => {
  // Không có cờ thì giao diện đọc kind từ spec null ra SKILL và giấu ô bậc bằng.
  assert.ok(RUBRICS.includes('threshold_pending'), 'trang rubric không đọc threshold_pending');
  assert.ok(EDITOR.includes('item.threshold_pending'), 'editor không cảnh báo khi thiếu ngưỡng');
});
