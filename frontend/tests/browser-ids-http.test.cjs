/**
 * Form công khai phải chạy được trên HTTP (VPS chưa có HTTPS).
 *
 * Lỗi thật: mở `http://<ip-vps>:3005/careers`, bấm vào một tin thì form không
 * mở, chỉ hiện "Trình duyệt không hỗ trợ tạo mã an toàn; cần HTTPS." Nguyên nhân
 * là `crypto.randomUUID()` — hàm này **chỉ có trong secure context** — trong khi
 * `crypto.getRandomValues()` cùng nằm trong `crypto`, cùng là CSPRNG, và **chạy
 * bình thường trên HTTP**.
 *
 * Nên cách sửa đúng không phải "hạ chuẩn ngẫu nhiên" mà là "đừng đòi đúng cái
 * hàm bị chặn": dựng mã từ `getRandomValues`, vốn chưa bao giờ thiếu.
 *
 * Test ở đây mô phỏng cả ba trạng thái trình duyệt, vì chỉ trạng thái thứ hai
 * mới tái hiện được lỗi:
 *   1. HTTPS hiện đại  — có `randomUUID`  → dùng nó (giữ mã chuẩn RFC 4122).
 *   2. HTTP thường     — KHÔNG có `randomUUID`, có `getRandomValues` → vẫn phải ra mã.
 *   3. Trình duyệt cực cũ — không có `getRandomValues` → trả null để trang báo đúng.
 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function loadTypeScriptModule(relativePath) {
  const filename = path.join(__dirname, '..', relativePath);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const loaded = { exports: {} };
  new Function('module', 'exports', 'require', output)(loaded, loaded.exports, require);
  return loaded.exports;
}

const { newPoolToken, newRequestId } = loadTypeScriptModule('src/lib/browserIds.ts');

/** Chạy `fn` với `globalThis.crypto` thay thế, rồi khôi phục. */
function withCrypto(fake, fn) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: fake, configurable: true, writable: true });
  try { return fn(); } finally {
    if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor);
    else delete globalThis.crypto;
  }
}

// Trình duyệt thật trên HTTP: KHÔNG có randomUUID, có getRandomValues.
// Đổ đầy số tăng dần để khẳng định được giá trị, không phải chỉ khác null.
// Bộ đếm nằm NGOÀI hàm: mỗi lần tạo fake mới mà seed lại về 0 thì hai lần gọi
// liên tiếp ra cùng mã, và ta sẽ tưởng code sinh hằng số.
let httpSeed = 0;
function httpBrowserCrypto() {
  return {
    getRandomValues(array) {
      for (let i = 0; i < array.length; i += 1) { array[i] = (httpSeed += 7) % 256; }
      return array;
    },
  };
}

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

test('HTTP (không có randomUUID) vẫn sinh được request_id đúng dạng UUID', () => {
  const value = withCrypto(httpBrowserCrypto(), () => newRequestId());
  assert.notEqual(value, null, 'HTTP thiếu randomUUID không được coi là trình duyệt hỏng');
  // Backend nhận `request_id: UUID` qua Form — sai dạng là 422, form vẫn chết.
  assert.match(value, UUID_SHAPE, `request_id không đúng dạng UUID: ${value}`);
});

test('HTTP vẫn sinh được pool_token 64 ký tự hex', () => {
  const value = withCrypto(httpBrowserCrypto(), () => newPoolToken());
  assert.notEqual(value, null);
  // Máy chủ kiểm `re.fullmatch(r'[0-9a-f]{64}', pool_token)` → sai là 400.
  assert.match(value, /^[0-9a-f]{64}$/, `pool_token sai định dạng: ${value}`);
});

test('mã sinh trên HTTP vẫn ngẫu nhiên, không phải hằng số', () => {
  const first = withCrypto(httpBrowserCrypto(), () => newRequestId());
  const second = withCrypto(httpBrowserCrypto(), () => newRequestId());
  assert.notEqual(first, second, 'hai lần gọi ra cùng mã — đang dùng hằng số chứ không phải CSPRNG');
});

test('có randomUUID thì dùng nguyên hàm của trình duyệt', () => {
  let calls = 0;
  const fake = {
    randomUUID: () => { calls += 1; return '11111111-2222-3333-4444-555555555555'; },
    getRandomValues: (array) => array,
  };
  const value = withCrypto(fake, () => newRequestId());
  assert.equal(value, '11111111-2222-3333-4444-555555555555');
  assert.equal(calls, 1);
});

test('randomUUID ném lỗi (trình duyệt cũ) thì rơi xuống đường dự phòng, không chặn', () => {
  const fake = httpBrowserCrypto();
  fake.randomUUID = () => { throw new Error('không phải secure context'); };
  const value = withCrypto(fake, () => newRequestId());
  assert.match(value, UUID_SHAPE, 'không được để lỗi của randomUUID làm hỏng form');
});

test('không có nguồn ngẫu nhiên nào thì trả null để trang báo đúng', () => {
  assert.equal(withCrypto({}, () => newRequestId()), null);
  assert.equal(withCrypto({}, () => newPoolToken()), null);
  assert.equal(withCrypto(undefined, () => newRequestId()), null);
});

test('trang tuyển dụng không còn đòi randomUUID và không đổ lỗi cho HTTPS', () => {
  // Khoá ở mức trang: helper đúng mà trang vẫn tự kiểm `randomUUID` thì lỗi
  // vẫn còn nguyên trên VPS.
  const raw = fs.readFileSync(path.join(__dirname, '..', 'src/app/careers/page.tsx'), 'utf8');
  // Bỏ chú thích: chính lời giải thích cũng nhắc tên `randomUUID`, và bắt nhầm
  // chữ trong chú thích là test tự đỏ vô cớ.
  const page = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.match(page, /newRequestId\(\)/, 'trang phải dùng helper dùng chung');
  assert.match(page, /newPoolToken\(\)/);
  assert.doesNotMatch(page, /crypto\.randomUUID\(\)/, 'còn gọi thẳng randomUUID — HTTP sẽ chết');
  assert.doesNotMatch(page, /không hỗ trợ tạo mã an toàn; cần HTTPS/,
    'câu báo cũ đổ lỗi cho HTTPS, sai nguyên nhân khi trình duyệt có getRandomValues');
});
