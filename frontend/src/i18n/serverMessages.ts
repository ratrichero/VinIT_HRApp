import english from './en.json';
import { getStoredLocale } from './I18nProvider';
import { translate, type Locale } from './translate';

const known: Record<string, string> = english;
const englishToVietnamese: Record<string, string> = {
  'Admin role required for this endpoint': 'Chỉ quản trị viên mới có quyền truy cập.',
  'Application not found': 'Không tìm thấy hồ sơ ứng viên.',
  'Authentication required': 'Vui lòng đăng nhập.',
  'Authentication service is not configured': 'Dịch vụ xác thực chưa được cấu hình.',
  'Authentication verification is not configured': 'Xác minh đăng nhập chưa được cấu hình.',
  'Could not generate file access URL': 'Không thể tạo liên kết xem tệp.',
  'Could not validate credentials': 'Không thể xác thực thông tin đăng nhập.',
  'Invalid file location': 'Vị trí tệp không hợp lệ.',
  'Invalid file path': 'Đường dẫn tệp không hợp lệ.',
  'Invalid position id': 'Mã vị trí không hợp lệ.',
  'Invalid user credentials': 'Thông tin đăng nhập không hợp lệ.',
  'Required role is not assigned': 'Tài khoản chưa được phân công vai trò cần thiết.',
  'Storage backend is not configured': 'Dịch vụ lưu trữ chưa được cấu hình.',
  'Supabase storage is not configured': 'Kho lưu trữ Supabase chưa được cấu hình.',
  'You do not have permission to access this position': 'Bạn không có quyền truy cập vị trí này.',
  'Cannot run assessment: criteria have not been approved by HR and Hiring Manager': 'Tiêu chí cần được HR và Hiring Manager duyệt trước khi đánh giá.',
  'External AI endpoints are disabled by configuration': 'Cấu hình không cho phép endpoint AI bên ngoài.',
  'External AI endpoints require HTTPS': 'Endpoint AI bên ngoài phải dùng HTTPS.',
  'Position not found': 'Không tìm thấy vị trí.',
  'Operation not found': 'Không tìm thấy tác vụ.',
  'LLM_API_BASE is not configured': 'Chưa cấu hình endpoint AI.',
  'Invalid LLM API endpoint': 'Endpoint AI không hợp lệ.',
  "Máy chủ chưa được cấu hình để gọi AI ra bên ngoài. Việc này chỉ Quản trị viên hệ thống làm được (bật ALLOW_EXTERNAL_API trong tệp cấu hình của máy chủ rồi khởi động lại). Báo Quản trị viên, không cần thử lại.": "This server is not allowed to call external AI. Only a system administrator can change this (enable ALLOW_EXTERNAL_API in the server configuration and restart). Please report it to your administrator; retrying will not help.",
  "Máy chủ chưa có cấu hình AI. Báo Quản trị viên thiết lập ở mục Quản trị → AI.": "The server has no AI configuration yet. Ask an administrator to set it up under Admin → AI.",
  "Cấu hình AI trên máy chủ không hợp lệ. Báo Quản trị viên kiểm tra lại địa chỉ và mô hình ở mục Quản trị → AI.": "The server's AI configuration is invalid. Ask an administrator to check the endpoint and model under Admin → AI.",
  "AI từ chối khoá truy cập: khoá sai, đã bị thu hồi hoặc hết hạn. Báo Quản trị viên cập nhật khoá ở mục Quản trị → AI.": "The AI provider rejected the access key: it is wrong, revoked or expired. Ask an administrator to update it under Admin → AI.",
  "Không tìm thấy mô hình AI đã cấu hình. Báo Quản trị viên kiểm tra tên mô hình ở mục Quản trị → AI.": "The configured AI model was not found. Ask an administrator to check the model name under Admin → AI.",
  "AI đang bị giới hạn tốc độ. Chờ một lát rồi thử lại.": "The AI provider is rate limiting requests. Wait a moment and try again.",
  "AI phản hồi quá lâu. Thử lại; nếu vẫn vậy thì báo Quản trị viên.": "The AI provider took too long to respond. Try again; if it keeps happening, tell an administrator.",
  "Nhà cung cấp AI đang gặp lỗi. Thử lại sau ít phút; nếu vẫn vậy thì báo Quản trị viên.": "The AI provider is having problems. Try again in a few minutes; if it keeps happening, tell an administrator.",
  "Máy chủ không kết nối được tới nhà cung cấp AI. Thử lại; nếu vẫn vậy thì báo Quản trị viên.": "The server could not reach the AI provider. Try again; if it keeps happening, tell an administrator.",
  "AI trả về nội dung không đọc được. Thử lại — lỗi này thường chỉ xảy ra một lần.": "The AI returned unreadable content. Try again — this usually happens only once.",
  "AI từ chối yêu cầu này. Kiểm tra lại nội dung JD rồi thử lại.": "The AI rejected this request. Check the job description and try again.",
  "Không gọi được AI. Thử lại; nếu vẫn vậy thì báo Quản trị viên kèm thời điểm bạn thử.": "Could not reach the AI. Try again; if it keeps happening, tell an administrator with the time you tried.",
};

export function localizeServerMessage(message: unknown, locale: Locale = getStoredLocale()): string {
  if (typeof message !== 'string') return translate('Dữ liệu gửi đi không hợp lệ.', locale);
  if (locale === 'vi') {
    if (englishToVietnamese[message]) return englishToVietnamese[message];
    if (known[message] || /[À-ỹĐđ]/.test(message)) return message;
    return translate('Không thể hoàn tất yêu cầu. Vui lòng thử lại.', locale);
  }
  if (known[message]) return known[message];
  if (englishToVietnamese[message] || Object.values(known).includes(message)) return message;
  // Avoid displaying untranslated or potentially sensitive server exceptions.
  return translate('Không thể hoàn tất yêu cầu. Vui lòng thử lại.', locale);
}
