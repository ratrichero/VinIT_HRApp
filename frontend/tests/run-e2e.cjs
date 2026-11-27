#!/usr/bin/env node
// Chạy các bài e2e theo `tests/e2e-manifest.cjs`, mỗi file một tiến trình riêng.
//
// Mỗi bài e2e vốn là một script độc lập: nó tự mở Chromium, tự chặn `/v1`, tự
// khẳng định rồi thoát. Chạy cả bộ bằng một script nghĩa là phải nói rõ **bài
// nào đỏ** và **đỏ vì gì**, chứ không phải chỉ một dòng "exit 1" — trước đây
// không có cách nào chạy cả bộ, nên cũng không ai biết cái gì đang hỏng.
//
// Dùng:
//   HRA_E2E_BASE_URL=http://127.0.0.1:3000 node tests/run-e2e.cjs            # tất cả
//   ... node tests/run-e2e.cjs --group green                                 # nhóm CI chạy
//   ... node tests/run-e2e.cjs --group green --only sticky                   # một phần
//   ... node tests/run-e2e.cjs --timeout 240                                 # trần mỗi bài (giây)
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { GREEN, RED, NEEDS_STACK, ALL } = require('./e2e-manifest.cjs');

const GROUPS = { green: GREEN, red: RED.map(e => e.file), 'needs-stack': NEEDS_STACK.map(e => e.file), all: ALL };
const REASON = new Map([...RED, ...NEEDS_STACK].map(e => [e.file, e.why]));

function flag(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const group = flag('--group', 'all');
const only = flag('--only', null);
const timeoutSeconds = Number(flag('--timeout', '180'));

if (!GROUPS[group]) {
  console.error(`Nhóm không có: ${group}. Chọn một trong: ${Object.keys(GROUPS).join(', ')}.`);
  process.exit(2);
}

const base = process.env.HRA_E2E_BASE_URL;
if (!base) {
  console.error(
    'Thiếu HRA_E2E_BASE_URL. Mọi bài e2e chỉ chạy với server cục bộ dùng một lần:\n'
      + '  npm run build && npx next start -p 3000 &\n'
      + '  HRA_E2E_BASE_URL=http://127.0.0.1:3000 npm run test:e2e',
  );
  process.exit(2);
}

(async () => {
  // Server chết thì mọi bài đều đỏ với "Target page has been closed" — kiểm một
  // lần trước, để không ai đọc 32 lỗi giả.
  let reachable = false;
  try {
    const response = await fetch(new URL('/dashboard', base), { signal: AbortSignal.timeout(15000) });
    reachable = response.status < 500;
  } catch (error) {
    reachable = false;
  }
  if (!reachable) {
    console.error(`Không kết nối được server ở ${base}. Dựng server rồi chạy lại.`);
    process.exit(2);
  }

  const files = GROUPS[group].filter(file => !only || file.includes(only));
  if (!files.length) {
    console.error(`Không có bài nào khớp (nhóm ${group}${only ? `, --only ${only}` : ''}).`);
    process.exit(2);
  }

  console.log(`Chạy ${files.length} bài e2e (nhóm ${group}) trên ${base}, trần ${timeoutSeconds}s/bài.\n`);

  const failed = [];
  const startedAll = Date.now();
  for (const file of files) {
    const started = Date.now();
    const result = spawnSync(process.execPath, [path.join(__dirname, file)], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env, HRA_E2E_BASE_URL: base },
      timeout: timeoutSeconds * 1000,
      encoding: 'utf8',
    });
    const seconds = ((Date.now() - started) / 1000).toFixed(1);
    const timedOut = result.signal === 'SIGTERM' || result.error?.code === 'ETIMEDOUT';
    const ok = result.status === 0 && !timedOut;

    if (ok) {
      console.log(`  PASS  ${file}  ${seconds}s`);
      continue;
    }

    const output = `${result.stdout || ''}${result.stderr || ''}`.trim();
    const firstError = output.split('\n').find(line => /Error|assert|Timeout|Expected/.test(line)) || output.slice(-300);
    console.log(`  FAIL  ${file}  ${seconds}s${timedOut ? ` (quá ${timeoutSeconds}s)` : ''}`);
    console.log(`        ${firstError.trim().slice(0, 400)}`);
    if (REASON.has(file)) console.log(`        đã ghi trong manifest: ${REASON.get(file)}`);
    failed.push(file);
  }

  const total = ((Date.now() - startedAll) / 1000).toFixed(1);
  console.log(`\n${files.length - failed.length}/${files.length} xanh, ${failed.length} đỏ, ${total}s.`);
  if (failed.length) {
    console.log(`Đỏ: ${failed.join(', ')}`);
    process.exit(1);
  }
})();
