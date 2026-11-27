const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

// Test the actual TypeScript helper without adding a separate test framework.
const source = path.join(__dirname, '../src/i18n/translate.ts');
const transpiled = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2020 },
}).outputText;
const loaded = new Module(source, module);
loaded.filename = source;
loaded.paths = Module._nodeModulePaths(path.dirname(source));
loaded._compile(transpiled, source);
const { translate } = loaded.exports;

test('Vietnamese defaults and English translations keep API-independent labels', () => {
  assert.equal(translate('Vị trí tuyển dụng', 'vi'), 'Vị trí tuyển dụng');
  assert.equal(translate('Vị trí tuyển dụng', 'en'), 'Recruitment positions');
  assert.equal(translate('Đang xem', 'en'), 'In review');
  assert.equal(translate('Nguồn dữ liệu người dùng', 'en'), 'Nguồn dữ liệu người dùng');
});

test('interpolation and existing alerts switch languages in both directions', () => {
  const vi = 'Đã chọn {0} hồ sơ để chia sẻ';
  // Use a dictionary template that is also used by the interface.
  assert.equal(translate('Trang {0} · Đã xác minh', 'en', 3), 'Page 3 · Verified');
  assert.equal(translate('Page 3 · Verified', 'vi'), 'Trang 3 · Đã xác minh');
  assert.equal(translate('Trang 3 · Đã xác minh', 'en'), 'Page 3 · Verified');
  assert.equal(translate('You do not have permission to access this position', 'vi'), 'Bạn không có quyền truy cập vị trí này.');
  assert.equal(translate('Bạn không có quyền truy cập vị trí này.', 'en'), 'You do not have permission to access this position');
  assert.equal(translate(vi, 'vi', 2), 'Đã chọn 2 hồ sơ để chia sẻ');
});

// Vietnamese-only letters: tells a human label apart from a code such as
// 'IN_REVIEW' or 'application/pdf', which must never need a translation.
const VIETNAMESE = /[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]/i;
const EQUALITY = new Set([
  ts.SyntaxKind.EqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsToken,
  ts.SyntaxKind.EqualsEqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsEqualsToken,
]);
const isText = node => Boolean(node) && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node));

/**
 * Keys the interface will ask the dictionary for, read from the syntax tree (so
 * comments and docs are never mistaken for labels):
 *  - `t('literal')` anywhere under src/;
 *  - every Vietnamese literal in src/lib, because those are the labels and
 *    messages the UI translates later (`t(LABELS[x])`) or renders as an error.
 * A Vietnamese literal compared against server data is a contract, not a label,
 * so it is skipped.
 */
function translationKeys(file, content) {
  const source = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.ES2020,
    true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const inLib = file.includes(`${path.sep}src${path.sep}lib${path.sep}`);
  const keys = new Set();
  const visit = node => {
    const argument = ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't'
      ? node.arguments[0] : null;
    if (isText(argument)) keys.add(argument.text);
    else if (inLib && isText(node) && VIETNAMESE.test(node.text)
      && !(ts.isBinaryExpression(node.parent) && EQUALITY.has(node.parent.operatorToken.kind))) {
      keys.add(node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return keys;
}

test('all literal UI translation keys have an English entry', () => {
  const dictionary = require('../src/i18n/en.json');
  const root = path.join(__dirname, '../src');
  const missing = [];
  let scanned = 0;
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) { walk(file); continue; }
      if (!/\.tsx?$/.test(file) || file.endsWith('.d.ts')) continue;
      if (file.includes(`${path.sep}i18n${path.sep}`)) continue;
      scanned += 1;
      const content = fs.readFileSync(file, 'utf8');
      for (const key of translationKeys(file, content)) {
        if (!(key in dictionary)) missing.push(`${path.relative(root, file)}: ${key}`);
      }
    }
  }
  walk(root);
  assert.ok(scanned > 0, 'the scan must actually read source files');
  assert.deepEqual(missing, []);
});

// ---------------------------------------------------------------------------
// Hai lỗi im lặng của từ điển. Cả hai đều "xanh" với test cũ vì test cũ chỉ
// kiểm **có entry**, không kiểm entry đó nói gì.
// ---------------------------------------------------------------------------

/**
 * Khoá được phép giữ nguyên tiếng Việt làm bản dịch. Chỉ dành cho **tên riêng
 * và mã** — thứ không có bản dịch tiếng Anh trung thực. Không thêm câu giao
 * diện vào đây: mỗi dòng thêm vào là một chỗ người dùng tiếng Anh vẫn đọc tiếng
 * Việt. Giá trị là lý do, để người sau không phải đoán.
 */
const UNTRANSLATED_EXEMPT = {
  // Ví dụ khi cần: 'VinUni': 'tên trường, giữ nguyên ở mọi ngôn ngữ',
};

/**
 * Giá trị tiếng Anh được phép trùng giữa nhiều khoá. `translate` dựng bảng
 * nghịch (Anh → Việt); trùng giá trị nghĩa là dịch ngược ra một khoá khác với
 * khoá đã sinh ra nó. Cách đúng để hết trùng là **gộp hai khoá tiếng Việt**
 * (nếu cùng nghĩa) hoặc chọn bản dịch khác nhau (nếu khác nghĩa) — không phải
 * thêm vào danh sách này.
 */
const DUPLICATE_VALUE_EXEMPT = {
  // 'Ví dụ': 'lý do cụ thể vì sao hai khoá buộc phải cùng một câu tiếng Anh',
};

test('không có khoá nào trả về y nguyên tiếng Việt khi giao diện là tiếng Anh', () => {
  const dictionary = require('../src/i18n/en.json');
  const untranslated = Object.entries(dictionary)
    .filter(([key, value]) => value === key && VIETNAMESE.test(key))
    .map(([key]) => key)
    .filter(key => !(key in UNTRANSLATED_EXEMPT));
  assert.deepEqual(
    untranslated,
    [],
    'Những khoá này có giá trị y nguyên khoá tiếng Việt, nên giao diện tiếng Anh hiện tiếng Việt: '
      + `${JSON.stringify(untranslated)}. Dịch thật, hoặc thêm vào UNTRANSLATED_EXEMPT kèm lý do `
      + '(chỉ tên riêng/mã).',
  );
});

test('giá trị tiếng Anh là duy nhất để dịch ngược không nhập nhằng', () => {
  const dictionary = require('../src/i18n/en.json');
  const byValue = new Map();
  for (const [key, value] of Object.entries(dictionary)) {
    if (value in DUPLICATE_VALUE_EXEMPT) continue;
    if (!byValue.has(value)) byValue.set(value, []);
    byValue.get(value).push(key);
  }
  const collisions = [...byValue.entries()]
    .filter(([, keys]) => keys.length > 1)
    .map(([value, keys]) => ({ value, keys }));
  assert.deepEqual(
    collisions,
    [],
    'Hai khoá khác nhau cùng một bản dịch làm bảng nghịch Anh → Việt chọn sai khoá: '
      + `${JSON.stringify(collisions)}. Gộp hai khoá nếu cùng nghĩa, hoặc chọn bản dịch khác nếu khác nghĩa.`,
  );
});

test('dịch ngược trả lại đúng khoá tiếng Việt đã sinh ra nó', () => {
  // Chốt chặn cho chính test trên: nếu bảng nghịch hỏng vì lý do khác (khoá bị
  // ghi đè, dấu câu lệch), phép dịch vòng tròn sẽ lộ ra.
  const dictionary = require('../src/i18n/en.json');
  const sample = Object.entries(dictionary)
    .filter(([key, value]) => VIETNAMESE.test(key) && !key.includes('{0}') && key.length < 60)
    .slice(0, 40);
  assert.ok(sample.length > 0, 'phải có mẫu để kiểm');
  for (const [key, value] of sample) {
    assert.equal(translate(value, 'vi'), key, `dịch ngược "${value}" ra khoá khác "${key}"`);
  }
});
