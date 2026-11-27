"""Thông báo 422: đủ để sửa, nhưng không lộ dữ liệu đã gửi.

Bối cảnh: handler cũ nuốt **mọi** lỗi 422 thành "Dữ liệu gửi đi không hợp lệ."
Lý do nuốt là đúng — Pydantic hay nhét nguyên giá trị đã gửi vào `input`, kể cả
mật khẩu và token. Nhưng nó nuốt cả câu do chính mình viết trong
`@model_validator`, ví dụ "Tiêu chí số năm cần min_years". Kết quả: HR bấm Lưu,
nhận một câu vô nghĩa, và không biết phải sửa ô nào.

Nay phân biệt hai loại:

* `value_error` — câu do ta kiểm soát, không chứa dữ liệu người dùng → trả về.
* các loại khác — Pydantic tự soạn và hay kèm `input` → vẫn câu chung.
"""
import pytest
from pydantic import BaseModel, Field, model_validator
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app


class _Rule(BaseModel):
    kind: str = 'A'
    secret: str = Field(max_length=5)

    @model_validator(mode='after')
    def business_rule(self):
        if self.kind == 'B':
            raise ValueError('Tiêu chí loại B cần thêm thông tin')
        return self


@pytest.fixture()
def client():
    """App thật (để dùng đúng handler đã đăng ký), cộng một route thử."""
    app: FastAPI = create_app()

    inner = FastAPI()

    @inner.post('/probe')
    def probe(body: _Rule):
        return {'ok': True}

    # chuyển handler của app thật sang app thử
    for exc_type, handler in app.exception_handlers.items():
        inner.add_exception_handler(exc_type, handler)
    return TestClient(inner)


def test_business_rule_message_reaches_the_user(client):
    """Câu trong validator là thứ HR cần thấy để biết sửa gì."""
    response = client.post('/probe', json={'kind': 'B', 'secret': 'abc'})
    assert response.status_code == 422
    assert 'loại B cần thêm thông tin' in response.json()['detail']


def test_schema_level_error_keeps_the_generic_message(client):
    """Lỗi độ dài là lỗi định dạng, không phải lời khuyên sửa gì."""
    response = client.post('/probe', json={'kind': 'A', 'secret': 'quá dài rồi'})
    assert response.status_code == 422
    assert response.json()['detail'] == 'Dữ liệu gửi đi không hợp lệ.'


def test_submitted_values_are_never_echoed_back(client):
    """Điều quan trọng nhất: body không được quay lại trong phản hồi.

    Pydantic đặt giá trị đã gửi vào `input` của mỗi lỗi. Nếu trả lỗi thô thì
    mật khẩu và token thiết lập cũng quay lại — đúng thứ handler cũ chặn.
    """
    marker = 'MAT-KHAU-BI-MAT-9f3a'
    response = client.post('/probe', json={'kind': 'A', 'secret': marker})
    assert marker not in response.text
    assert 'MAT-KHAU' not in response.text
