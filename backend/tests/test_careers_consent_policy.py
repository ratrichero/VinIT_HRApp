"""Chính sách đồng ý và thời hạn lưu hồ sơ ở đường nộp công khai.

Ba thay đổi được khoá ở đây, tất cả đều là **cam kết với ứng viên** chứ không
phải chi tiết kỹ thuật — nên chúng phải có test, không thể để trôi:

1. Nhận email thật. Trước đây form công khai từ chối mọi địa chỉ không kết thúc
   bằng `@example.test` (400), trong khi nhãn ghi "Email tổng hợp". Nay nhãn là
   "Email" và backend nhận email thật.

2. Bằng chứng consent ghi cho MỌI hồ sơ, với thời hạn 12 tháng. Câu đồng ý trên
   form gộp hai việc (nộp hồ sơ + lưu hồ sơ để dùng cho nhu cầu tuyển dụng sau),
   nên nộp là đã đồng ý. Không có dòng `talent_pool_consents` nghĩa là sau này
   không trả lời được "hồ sơ này được giữ đến bao giờ, theo bản thông báo nào".

3. Thời hạn trong mã phải khớp con số đã hứa trên giao diện. Sửa 365 thành 7 ở
   một bên là nói một đằng làm một nẻo — loại lỗi không ai thấy cho tới khi có
   yêu cầu xoá dữ liệu.

Phần chạy được không cần PostgreSQL: kiểm hằng số, kiểm bằng chứng trong mã, và
kiểm `create_consent` từ chối đầu vào hỏng. Phần cần DB (dòng consent thật sự
được ghi) nằm ở `test_careers_real_intake.py`, chạy trên PostgreSQL dùng một lần.
"""
import inspect
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.api import careers_intake
from app.services.talent_pool import create_consent

SOURCE = Path(careers_intake.__file__).read_text(encoding='utf-8')


def _code_only(source: str) -> str:
    """Bỏ chú thích: chính lời giải thích cũng nhắc `@example.test`, bắt nhầm
    chữ trong chú thích là test tự đỏ vô cớ."""
    without_block = re.sub(r'"""[\s\S]*?"""', '', source)
    return re.sub(r'^\s*#.*$', '', without_block, flags=re.M)


CODE = _code_only(SOURCE)


def test_accepts_real_email_addresses():
    """Không còn ràng buộc `@example.test` trong mã thực thi."""
    assert '@example.test' not in CODE, (
        'đường nộp công khai vẫn còn chặn email thật — nhãn "Email" trên form '
        'sẽ khiến ứng viên gõ email thật rồi bị từ chối 400'
    )
    # Và vẫn phải kiểm hợp lệ: bỏ chặn không có nghĩa là nhận chuỗi bất kỳ.
    assert 'validate_email' in CODE, 'mất bước kiểm địa chỉ email'
    # `test_environment=True` là chế độ dành cho thư viện email-validator khi
    # chạy test; bỏ đi để không vô tình nới lỏng việc kiểm tên miền.
    assert 'test_environment' not in CODE, 'còn chế độ test_environment khi kiểm email thật'


def test_retention_window_is_twelve_months():
    """Cam kết 12 tháng nằm ở một chỗ, và đúng là 12 tháng."""
    assert careers_intake.RETENTION_DAYS == 365, (
        'RETENTION_DAYS phải là 365: form đã hứa "12 tháng" với ứng viên'
    )


def test_consent_is_written_for_every_application_not_only_opt_in():
    """Bằng chứng consent không được nằm trong `if pool_opt_in:`.

    Câu đồng ý trên form là bắt buộc và đã gộp hai mục đích, nên mọi hồ sơ đều
    phải có dòng consent. Nếu vẫn nằm trong nhánh `if`, hồ sơ không tick pool
    sẽ không có bằng chứng — và câu đồng ý bắt buộc trở thành lời hứa suông.
    """
    require = inspect.getsource(careers_intake._commit_intake)
    assert 'create_consent(' in require, 'không còn ghi consent'
    # Tìm khối `if ...:` ngay trước lời gọi; nếu là `if pool_opt_in` thì sai.
    before = require[:require.index('create_consent(')]
    last_lines = [line for line in before.strip().splitlines()[-4:] if line.strip()]
    assert not any('if pool_opt_in' in line for line in last_lines), (
        'create_consent vẫn nằm trong nhánh `if pool_opt_in` — hồ sơ không chọn '
        'pool sẽ không có bằng chứng đồng ý'
    )


def test_consent_expiry_uses_the_retention_constant():
    """Hạn lưu phải lấy từ hằng số, không phải con số viết tay thứ hai."""
    require = inspect.getsource(careers_intake._commit_intake)
    assert 'timedelta(days=RETENTION_DAYS)' in require, (
        'hạn lưu không dùng RETENTION_DAYS — hai con số viết tay sẽ lệch nhau'
    )
    assert not re.search(r'timedelta\(days=\d+\)', require), (
        'còn con số ngày viết tay trong mã ghi consent'
    )


def test_notice_version_is_versioned_not_a_reused_test_label():
    """Bản thông báo phải mang số phiên bản của câu chữ mới.

    Dùng lại `synthetic-intake-test-v1` cho một câu đồng ý khác nghĩa là làm
    sai lệch bằng chứng: về sau tra ra sẽ tưởng ứng viên đồng ý với bản thử
    nghiệm 7 ngày.
    """
    notice = careers_intake.CONSENT_NOTICE
    assert '12m' in notice or '12' in notice, f'phiên bản thông báo không nói 12 tháng: {notice}'
    assert notice != 'synthetic-intake-test-v1', 'còn dùng nhãn thông báo của vòng thử nghiệm cũ'
    assert len(notice) <= 100, 'notice_version có CHECK độ dài 1..100 trong DB'


def test_create_consent_still_rejects_malformed_policy():
    """Chặn ở tầng dịch vụ vẫn còn: hạn không múi giờ, token sai dạng."""
    class _DB:
        def execute(self, *args, **kwargs):
            raise AssertionError('không được ghi DB khi đầu vào hỏng')

    expiry = datetime.now(timezone.utc) + timedelta(days=365)
    assert create_consent.__name__ and callable(create_consent)

    # Mất múi giờ → ValueError, không được ghi.
    with pytest.raises(ValueError):
        create_consent(_DB(), application_id='a', notice_version='v1',
                       consent_expires_at=datetime.now(), retention_expires_at=expiry)
    # Token sai định dạng → ValueError.
    with pytest.raises(ValueError):
        create_consent(_DB(), application_id='a', notice_version='v1',
                       consent_expires_at=expiry, retention_expires_at=expiry,
                       withdrawal_token='khong-phai-hex')
    # notice_version rỗng → ValueError.
    with pytest.raises(ValueError):
        create_consent(_DB(), application_id='a', notice_version='',
                       consent_expires_at=expiry, retention_expires_at=expiry)


def test_no_hardcoded_seven_day_window_remains():
    """Không còn hạn 7 ngày ở bất kỳ đâu trên đường nộp công khai."""
    assert not re.search(r'timedelta\(days=7\)', CODE), 'vẫn còn hạn 7 ngày'
    assert '7 ngày' not in CODE, 'còn câu chữ "7 ngày" trong mã thực thi'


def test_talent_pool_gate_does_not_block_consent_evidence():
    """Cờ Storage của Talent Pool không được chặn việc ghi bằng chứng consent.

    Nếu chặn 503 gắn vào bằng chứng (thay vì vào lựa chọn tái sử dụng), bật
    câu đồng ý bắt buộc sẽ làm mọi hồ sơ bị từ chối mỗi khi cờ đó tắt.
    """
    require = inspect.getsource(careers_intake._commit_intake)
    assert 'TALENT_POOL_STORAGE_READY' not in require, (
        'cờ Storage lọt vào bước ghi consent — tắt cờ là hỏng cả form'
    )
