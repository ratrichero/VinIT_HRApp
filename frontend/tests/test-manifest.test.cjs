// Test này canh chính việc test: mọi file *.test.cjs phải được khai trong
// package.json, nếu không nó sẽ không bao giờ chạy trên CI.
//
// Lý do tồn tại: 3 file test của đợt lịch phỏng vấn (37 test) đã nằm trong
// repo nhưng KHÔNG có trong test:unit. Chúng xanh trên máy người viết và
// không chạy ở đâu cả. Cùng loại lỗi với CI đỏ 11 ngày: tin vào thứ chưa
// thực sự chạy.
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

function declaredTestFiles() {
  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  const found = new Set();
  for (const script of Object.values(pkg.scripts || {})) {
    for (const token of String(script).split(/\s+/)) {
      if (token.includes('tests/') && token.endsWith('.cjs')) {
        found.add(token.replace(/^node\s+/, '').replace(/^tests\//, ''));
      }
    }
  }
  return found;
}

test('moi file test deu duoc khai trong package.json', () => {
  const declared = declaredTestFiles();
  const onDisk = fs.readdirSync(path.join(ROOT, 'tests'))
    .filter((name) => name.endsWith('.test.cjs'));
  const missing = onDisk.filter((name) => !declared.has(name));
  assert.deepStrictEqual(
    missing, [],
    'File test chưa được khai trong scripts của package.json nên không chạy trên CI: '
      + missing.join(', '),
  );
});

test('khong khai file test khong ton tai', () => {
  const declared = declaredTestFiles();
  const onDisk = new Set(fs.readdirSync(path.join(ROOT, 'tests')));
  const ghosts = [...declared].filter((name) => !onDisk.has(name));
  assert.deepStrictEqual(ghosts, [], 'Khai file test không có thật: ' + ghosts.join(', '));
});

// ---------------------------------------------------------------------------
// e2e: cùng một luật, nhưng nguồn khai là `tests/e2e-manifest.cjs` — vì 45 bài
// e2e không thể là 45 script riêng trong package.json mà vẫn đọc được.
// ---------------------------------------------------------------------------

const E2E_MANIFEST = require('./e2e-manifest.cjs');

function e2eOnDisk() {
  return fs.readdirSync(path.join(ROOT, 'tests')).filter(name => name.endsWith('.e2e.cjs'));
}

test('moi file e2e deu co trong e2e-manifest', () => {
  const listed = new Set(E2E_MANIFEST.ALL);
  const missing = e2eOnDisk().filter(name => !listed.has(name));
  assert.deepStrictEqual(
    missing, [],
    'File e2e chưa có trong tests/e2e-manifest.cjs nên không runner nào chạy nó: ' + missing.join(', '),
  );
});

test('e2e-manifest khong khai file khong ton tai, va khong khai trung', () => {
  const onDisk = new Set(e2eOnDisk());
  const ghosts = E2E_MANIFEST.ALL.filter(name => !onDisk.has(name));
  assert.deepStrictEqual(ghosts, [], 'Khai file e2e không có thật: ' + ghosts.join(', '));

  const seen = new Set();
  const twice = E2E_MANIFEST.ALL.filter(name => (seen.has(name) ? true : (seen.add(name), false)));
  assert.deepStrictEqual(twice, [], 'File e2e nằm ở nhiều nhóm: ' + twice.join(', '));
});

test('nhom e2e xanh phai duoc CI goi that', () => {
  // Nhóm xanh chỉ có nghĩa nếu có job chạy nó. Script khai mà CI không gọi là
  // đúng lỗi ban đầu: test không chạy ở đâu cả.
  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  assert.ok(pkg.scripts['test:e2e:green'], 'thiếu script test:e2e:green');
  assert.match(pkg.scripts['test:e2e:green'], /run-e2e\.cjs --group green/);
  assert.ok(pkg.scripts['test:e2e'], 'thiếu script test:e2e chạy cả bộ');

  const workflow = fs.readFileSync(path.join(ROOT, '..', '.github', 'workflows', 'ci.yml'), 'utf8');
  assert.match(
    workflow, /npm run test:e2e:green/,
    'CI không có bước nào chạy nhóm e2e xanh, nên nhóm đó vẫn không chạy ở đâu cả',
  );
});
