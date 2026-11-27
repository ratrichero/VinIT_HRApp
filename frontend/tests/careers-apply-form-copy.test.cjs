/**
 * Nhãn và câu đồng ý trên form nộp hồ sơ công khai.
 *
 * Đây là câu chữ pháp lý mà ứng viên thật đọc: nhãn "Tên tổng hợp" từng làm
 * người nộp tưởng đây là form demo, còn câu đồng ý cũ nói về một "Talent Pool
 * thử nghiệm 7 ngày" không còn tồn tại. Test khoá cả nội dung lẫn vài tính chất
 * dễ mất khi sửa nhanh:
 *
 *  - câu đồng ý phải nêu **số tháng cụ thể** và **quyền rút lại**;
 *  - ô đồng ý phải **bắt buộc** (gộp một câu theo yêu cầu);
 *  - phải có lời nhắc khi bấm Gửi mà chưa tick — `required` của trình duyệt
 *    không đủ, form dài nên thông báo nằm ngoài tầm nhìn.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (...p) => fs.readFileSync(path.join(__dirname, '..', ...p), 'utf8');
const PAGE = read('src', 'app', 'careers', 'page.tsx');
const EN = JSON.parse(read('src', 'i18n', 'en.json'));

test('ba trường dùng nhãn cho người nộp thật, không phải "tổng hợp"', () => {
  assert.match(PAGE, /label=\{t\('Tên ứng viên'\)\}/, 'thiếu nhãn "Tên ứng viên"');
  assert.match(PAGE, /label=\{t\('Email'\)\}/, 'nhãn email phải là "Email"');
  assert.match(PAGE, /label=\{t\('Điện thoại'\)\}/, 'nhãn điện thoại phải là "Điện thoại"');
  // Nhãn cũ khiến ứng viên tưởng chỉ được gõ dữ liệu giả.
  assert.doesNotMatch(PAGE, /Tên tổng hợp/, 'còn nhãn "Tên tổng hợp"');
  assert.doesNotMatch(PAGE, /Email tổng hợp/, 'còn nhãn "Email tổng hợp"');
  assert.doesNotMatch(PAGE, /@example\.test/, 'còn nhắc @example.test trên giao diện');
});

test('cảnh báo "chỉ dùng dữ liệu tổng hợp" đã bỏ', () => {
  // Backend nay nhận email thật; giữ cảnh báo này là mâu thuẫn trực tiếp với form.
  assert.doesNotMatch(PAGE, /Chỉ kiểm thử với CV và thông tin tổng hợp/,
    'còn cảnh báo chỉ nhận dữ liệu tổng hợp');
});

test('câu đồng ý gộp một câu, nêu 12 tháng và quyền rút', () => {
  const match = PAGE.match(/label=\{<Typography[^>]*>\s*\{t\('(Tôi đồng ý nộp hồ sơ[^']*)'\)\}/);
  assert.ok(match, 'không tìm thấy câu đồng ý gộp');
  const copy = match[1];
  assert.match(copy, /12 tháng/, 'câu đồng ý không nêu thời hạn cụ thể');
  assert.match(copy, /rút lại/, 'câu đồng ý không nêu quyền rút lại');
  assert.match(copy, /VinCareer/, 'câu đồng ý không nêu tên đơn vị giữ dữ liệu');
  // Câu cũ nói về Talent Pool 7 ngày — không còn đúng.
  assert.doesNotMatch(copy, /Talent Pool thử nghiệm trong 7 ngày/);
  assert.doesNotMatch(PAGE, /Talent Pool thử nghiệm trong 7 ngày/, 'còn câu Talent Pool cũ');
});

test('ô đồng ý là bắt buộc và có lời nhắc khi chưa tick', () => {
  // `[^>]*` không dùng được: chuỗi có `=>` trong `onChange`, dấu `>` đầu tiên
  // đó sẽ cắt ngang thẻ. Dùng `[\s\S]*?` cho tới `/>` đầu tiên.
  const checkbox = PAGE.match(/<Checkbox[\s\S]*?checked=\{optedIn\}[\s\S]*?\/>/);
  assert.ok(checkbox, 'không tìm thấy checkbox đồng ý');
  assert.match(checkbox[0], /required/, 'ô đồng ý phải bắt buộc');
  // `required` của trình duyệt không hiện thông báo ở cuối form dài.
  assert.match(PAGE, /if \(!optedIn\) \{ setConsentMissing\(true\); return; \}/,
    'thiếu chặn ở apply() khi chưa đồng ý');
  assert.match(PAGE, /consentMissing && <Alert/, 'thiếu lời nhắc hiển thị');
});

test('nút gửi không còn chữ "thử nghiệm"', () => {
  assert.match(PAGE, /\{t\('Gửi hồ sơ'\)\}/, 'nút gửi phải là "Gửi hồ sơ"');
  assert.doesNotMatch(PAGE, /Gửi hồ sơ thử nghiệm/);
  assert.doesNotMatch(PAGE, /CV tổng hợp/, 'còn nhãn "CV tổng hợp"');
});

test('mọi chuỗi mới đều có bản dịch tiếng Anh', () => {
  const strings = [
    'Tên ứng viên', 'Email', 'Điện thoại',
    'CV PDF hoặc DOCX, tối đa 10 MB', 'Gửi hồ sơ',
    'Bạn cần đọc và đồng ý câu trên trước khi gửi hồ sơ.',
  ];
  for (const s of strings) {
    assert.ok(EN[s], `thiếu bản dịch cho: ${s}`);
  }
  const consent = PAGE.match(/\{t\('(Tôi đồng ý nộp hồ sơ[^']*)'\)\}/);
  assert.ok(consent && EN[consent[1]], 'câu đồng ý chưa có bản dịch tiếng Anh');
});

test('12 tháng trên giao diện khớp 365 ngày ở backend', () => {
  // Hai nơi nói về cùng một cam kết. Lệch nhau là nói một đằng làm một nẻo —
  // loại lỗi chỉ lộ ra khi có yêu cầu xoá dữ liệu của ứng viên.
  const backend = read('..', 'backend', 'app', 'api', 'careers_intake.py');
  assert.match(backend, /RETENTION_DAYS = 365/, 'backend không còn 365 ngày');
  const consent = PAGE.match(/\{t\('(Tôi đồng ý nộp hồ sơ[^']*)'\)\}/);
  assert.match(consent[1], /12 tháng/, 'giao diện không còn nói 12 tháng');
});
