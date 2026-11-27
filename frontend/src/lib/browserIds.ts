/**
 * Sinh mã phía trình duyệt cho form công khai — chịu được cả khi trang chạy HTTP.
 *
 * `crypto.randomUUID()` **chỉ có trong secure context** (HTTPS hoặc localhost).
 * Mở trang tuyển dụng qua `http://<ip-vps>:3005` thì hàm đó là `undefined`, và
 * form trước đây chặn thẳng bằng câu "cần HTTPS" dù trình duyệt vẫn có nguồn
 * ngẫu nhiên mật mã học đầy đủ.
 *
 * `crypto.getRandomValues()` thì **không** bị giới hạn đó — nó chạy trên HTTP.
 * Vì vậy ở đây không hạ chuẩn ngẫu nhiên: mã được dựng từ cùng nguồn CSPRNG của
 * trình duyệt, chỉ khác là tự định dạng thay vì nhờ `randomUUID`.
 *
 * Đánh đổi của đường dự phòng, nói rõ để người sau không tưởng là tương đương:
 *
 *  - `request_id` mất nhóm version/variant của UUID (RFC 4122). Máy chủ dùng nó
 *    như một chuỗi định danh idempotency (`UUID` của FastAPI vẫn nhận dạng 8-4-4-4-12),
 *    nên 128 bit ngẫu nhiên là đủ; nó không phải thứ ai đó phân tích cấu trúc.
 *  - `pool_token` đã là hex 64 ký tự từ trước, không đổi.
 *
 * Trả `null` khi trình duyệt **không** có nguồn ngẫu nhiên nào — lúc đó mới là
 * chặn thật, và câu báo phải nói đúng là trình duyệt quá cũ chứ không đổ cho HTTPS.
 */

type CryptoLike = {
  randomUUID?: () => string;
  getRandomValues?: (array: Uint8Array) => Uint8Array;
};

function cryptoOf(): CryptoLike | null {
  const value = (globalThis as { crypto?: CryptoLike }).crypto;
  return value && typeof value === 'object' ? value : null;
}

/** 16 byte ngẫu nhiên, đóng gói thành chuỗi 8-4-4-4-12. */
function uuidFromRandomBytes(bytes: Uint8Array): string {
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Mã yêu cầu cho form nộp hồ sơ. `null` = trình duyệt không có nguồn ngẫu nhiên.
 */
export function newRequestId(): string | null {
  const crypto = cryptoOf();
  if (!crypto) return null;
  if (typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID();
    } catch {
      // Một số trình duyệt cũ có hàm nhưng ném lỗi khi không phải secure
      // context — rơi xuống đường dự phòng bên dưới thay vì chặn người dùng.
    }
  }
  if (typeof crypto.getRandomValues !== 'function') return null;
  return uuidFromRandomBytes(crypto.getRandomValues(new Uint8Array(16)));
}

/**
 * Mã rút lựa chọn talent pool: 32 byte → 64 ký tự hex, đúng định dạng máy chủ
 * kiểm (`[0-9a-f]{64}`). `null` = trình duyệt không có nguồn ngẫu nhiên.
 */
export function newPoolToken(): string | null {
  const crypto = cryptoOf();
  if (!crypto || typeof crypto.getRandomValues !== 'function') return null;
  return Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, '0')).join('');
}
