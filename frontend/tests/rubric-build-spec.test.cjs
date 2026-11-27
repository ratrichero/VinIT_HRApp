/**
 * `buildSpec` — dựng `requirement_spec` gửi lên máy chủ.
 *
 * Hàm này tồn tại vì một lỗi thật: giao diện chỉ cho HR chọn *loại* tiêu chí,
 * nên khi họ vừa đổi loại trên một tiêu chí chưa có spec, object gửi lên chỉ
 * có `{kind: 'YEARS'}`. Schema backend từ chối spec không nói được gì → mọi
 * lần đổi loại đều 422. `buildSpec` luôn kèm `terms` để câu đó không xảy ra.
 *
 * Cách nạp: biên dịch chính file TSX bằng `typescript` (đã có sẵn trong
 * node_modules, không thêm phụ thuộc), rồi thay `require` bằng một proxy rỗng.
 * Component không chạy ở phạm vi module — chỉ import và khai báo — nên nạp được
 * mà không cần React hay MUI thật. Trích hàm bằng regex thì mỏng manh: lần đầu
 * tôi thử đã vỡ vì dấu `{` trong `Record<string, unknown>` bị đếm là thân hàm.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const SRC_PATH = path.join(__dirname, '..', 'src', 'lib', 'requirementSpec.ts');

/** `require` giả: trả về chính nó cho mọi truy cập, đủ để import không nổ. */
function stubRequire() {
  const target = function stub() {};
  const proxy = new Proxy(target, {
    get: () => proxy,
    apply: () => proxy,
    construct: () => proxy,
  });
  return proxy;
}

function loadModule() {
  const source = fs.readFileSync(SRC_PATH, 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React,
    },
    fileName: SRC_PATH,
  }).outputText;

  const mod = { exports: {} };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', js)(mod, mod.exports, stubRequire());
  return mod.exports;
}

const { buildSpec } = loadModule();

const item = (over = {}) => ({
  name: 'Kinh nghiệm API',
  description: 'Ít nhất 3 năm',
  category: 'MUST_HAVE',
  weight_in_group: 50,
  expected_evidence_keywords: [],
  requirement_spec: null,
  evidence_guidance: null,
  ...over,
});

test('chưa có spec, chưa có từ khoá, không có tên → gửi null để máy tự suy từ chữ', () => {
  // Gửi {kind:'SKILL'} trần là spec vô nghĩa; schema sẽ từ chối.
  assert.strictEqual(buildSpec(null, '', ''), null);
});

test('đổi loại trên tiêu chí chưa có spec vẫn gửi được terms', () => {
  const spec = buildSpec({ kind: 'YEARS' }, 'python, fastapi', 'Kinh nghiệm API');
  assert.strictEqual(spec.kind, 'YEARS');
  assert.deepStrictEqual(spec.terms, ['python', 'fastapi']);
});

test('không có từ khoá thì lấy tên tiêu chí làm thuật ngữ, không để rỗng', () => {
  const spec = buildSpec({ kind: 'DEGREE' }, '', 'Bằng đại học');
  assert.deepStrictEqual(spec.terms, ['Bằng đại học']);
});

test('từ khoá nhiều dấu phẩy thừa được làm sạch', () => {
  const spec = buildSpec({}, ' python ,, fastapi , ', 'X');
  assert.deepStrictEqual(spec.terms, ['python', 'fastapi']);
});

test('đổi loại thì bỏ ngưỡng của loại cũ, không lưu rác chéo loại', () => {
  // Để min_years lại trên một tiêu chí SKILL là dữ liệu chết, và người đọc sau
  // không biết nó còn hiệu lực hay không.
  const spec = buildSpec(
    { kind: 'SKILL', min_years: 5, required_degree_level: 3 },
    'python', 'X',
  );
  assert.strictEqual(spec.min_years, null);
  assert.strictEqual(spec.required_degree_level, null);
});

test('giữ ngưỡng của đúng loại đang chọn', () => {
  const spec = buildSpec({ kind: 'YEARS', min_years: 4 }, 'python', 'X');
  assert.strictEqual(spec.kind, 'YEARS');
  assert.strictEqual(spec.min_years, 4);
});

test('spec hỏng (chuỗi thay vì object) không làm nổ trang', () => {
  // requirement_spec là JSONB tự do; dữ liệu cũ có thể là bất cứ thứ gì.
  const spec = buildSpec('rác', 'python', 'X');
  assert.strictEqual(spec.kind, 'SKILL');
  assert.deepStrictEqual(spec.terms, ['python']);
});

test('terms trong spec luôn khớp ô từ khoá, không phải hai danh sách lệch nhau', () => {
  // Nếu spec giữ terms cũ trong khi HR sửa ô từ khoá, máy dò theo spec còn
  // giao diện hiện theo ô — hai thứ khác nhau và không ai biết cái nào đúng.
  const spec = buildSpec(item({ requirement_spec: { kind: 'SKILL', terms: ['cũ'] } }), 'mới');
  assert.deepStrictEqual(spec.terms, ['mới']);
});

test('spec đang là LANGUAGE thì giữ nguyên ngôn ngữ, không xoá', () => {
  // buildSpec KHÔNG đổi kind — việc đó là của changeKind khi HR bấm ô chọn.
  // Ở đây kiểm điều ngược lại: đúng loại rồi thì ngưỡng của nó phải sống sót.
  const spec = buildSpec(
    { kind: 'LANGUAGE', required_languages: ['english'], required_ielts: 6.5 },
    'ielts', 'X',
  );
  assert.strictEqual(spec.kind, 'LANGUAGE');
  assert.deepStrictEqual(spec.required_languages, ['english']);
  assert.strictEqual(spec.required_ielts, 6.5);
});

test('ngưỡng của loại khác bị xoá khi spec đang là YEARS', () => {
  const spec = buildSpec(
    { kind: 'YEARS', min_years: 3, required_languages: ['english'] },
    'python', 'X',
  );
  assert.strictEqual(spec.kind, 'YEARS');
  assert.strictEqual(spec.min_years, 3);
  assert.deepStrictEqual(spec.required_languages, []);
});

test('form chặn trước khi gửi khi thiếu ngưỡng bắt buộc', () => {
  // Schema (audit M1) từ chối YEARS không có min_years, DEGREE không có bậc,
  // LANGUAGE không có ngôn ngữ/mức. Form phải nói rõ ở tiêu chí nào, thay vì
  // để 422 chung chung sau khi HR bấm Lưu.
  const PAGE = fs.readFileSync(
    path.join(__dirname, '..', 'src', 'app', 'rubrics', 'page.tsx'), 'utf8');
  assert.ok(PAGE.includes('const missingThreshold'), 'thiếu bước kiểm trước khi gửi');
  // Nay dùng `specProblem` chung thay vì ba nhánh chép tay — xem
  // requirement-spec-audit-fixes.test.cjs. Điều cần khoá ở đây là *có* bước kiểm.
  assert.ok(PAGE.includes('specProblem('), 'phải dùng hàm kiểm chung');
  assert.ok(PAGE.includes('threshold_pending'), 'phải chặn cả ca spec thiếu ngưỡng');
  // Và bước kiểm phải chạy TRƯỚC khi gọi API.
  const checkAt = PAGE.indexOf('const missing = missingThreshold();');
  const callAt = PAGE.indexOf('const result = creating ? await rubricApi.create');
  assert.ok(checkAt > 0 && callAt > 0 && checkAt < callAt, 'phải kiểm trước khi gọi create');
});
