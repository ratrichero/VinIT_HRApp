// Badge "việc cần làm" phải cập nhật khi đổi trang.
//
// Lỗi thật (từ freebuff): effect đọc `pathname` để bỏ qua /dashboard và với ý
// đồ "đổi trang là lúc cập nhật badge", nhưng deps chỉ có
// [authenticated, authScope]. Code và comment nói hai chuyện khác nhau: badge
// chỉ cập nhật một lần khi đăng nhập, rồi đứng im suốt phiên.
//
// eslint bắt được (react-hooks/exhaustive-deps) nên warning này là bug thật,
// không phải nhiễu — đừng tắt rule cho file này.
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = path.join(__dirname, '../src/components/layout/AppLayout.tsx');
const src = fs.readFileSync(SOURCE, 'utf8');

// Chỉ lấy thân effect chứa workQueueFetchedAt — tránh bắt nhầm effect khác.
function badgeEffect() {
  const anchor = src.indexOf('workQueueFetchedAt.current < 30_000');
  assert.ok(anchor !== -1, 'Không tìm thấy effect badge — code đã đổi cấu trúc, cập nhật test');
  const start = src.lastIndexOf('useEffect(', anchor);
  const end = src.indexOf('}, [', anchor);
  return src.slice(start, src.indexOf(']);', end) + 3);
}

test('effect badge có pathname trong dependency list', () => {
  const effect = badgeEffect();
  assert.match(effect, /if \(pathname === '\/dashboard'\) return/, 'effect phải còn đọc pathname');
  const deps = effect.slice(effect.lastIndexOf('}, ['));
  assert.match(deps, /pathname/, 'pathname được đọc trong effect nhưng thiếu trong deps: '
    + 'badge sẽ không cập nhật khi đổi trang');
});

test('có chốt chặn chống gọi lại liên tục', () => {
  // Không có chốt này thì thêm pathname vào deps sẽ thành vòng lặp: mỗi lần
  // setWorkCount làm component render, effect chạy lại, lại gọi API.
  assert.match(src, /workQueueFetchedAt\s*=\s*useRef\(0\)/, 'mất useRef chốt thời gian');
  assert.match(badgeEffect(), /workQueueFetchedAt\.current < 30_000/, 'mất kiểm tra giãn cách 30 giây');
});

test('đổi hồ sơ trong cùng danh sách không hỏi lại badge', () => {
  // Thêm `pathname` vào deps (test trên) sửa lỗi badge đứng im, nhưng `pathname`
  // đổi cả khi chỉ bấm `n` sang hồ sơ khác trong CÙNG vị trí — quyền và phạm vi
  // badge y nguyên. Không có chốt này thì mỗi lần bấm `n` (sau 30 giây) lại tốn
  // một request; freebuff đo được đúng ca đó ở `profile-transition-requests`.
  // Hai test phải cùng đúng — nên chốt phải dựa trên "màn hình", không phải
  // "đường dẫn đầy đủ".
  assert.match(src, /badgeScreenRef\s*=\s*useRef/, 'mất chốt màn hình đã hỏi badge');
  const effect = badgeEffect();
  assert.match(effect, /pathname\.replace\([^)]*applicants/, 'phải bỏ mã hồ sơ ở cuối đường dẫn');
  assert.match(effect, /badgeScreenRef\.current === badgeScreen/, 'phải so màn hình trước khi gọi');
  // So sánh phải đứng TRƯỚC lần gọi API, nếu không thì chốt vô tác dụng.
  assert.ok(effect.indexOf('badgeScreenRef.current === badgeScreen')
    < effect.indexOf('getWorkQueue'), 'chốt phải kiểm trước khi gọi API');
});
