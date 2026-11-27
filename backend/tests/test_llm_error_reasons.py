"""Lỗi AI phải nói được nguyên nhân, và nói theo VIỆC HR PHẢI LÀM.

Vì sao có tệp này: trước đây mọi lỗi AI đều ra một câu duy nhất — "kiểm tra cấu
hình và thử lại" — gộp ba tình huống đòi ba hành động khác hẳn:

* máy chủ chưa bật ``ALLOW_EXTERNAL_API`` → sửa ``.env``, HR không tự làm được
* khoá API sai/hết hạn → sửa trong Admin → AI, HR không tự làm được
* provider trả JSON hỏng → bấm lại là xong

HR đọc câu chung chung đó không biết phải làm gì, và hai trong ba trường hợp
họ không có quyền sửa.

Gốc rễ không phải thiếu thông tin — ``_call_llm_one`` đã phân loại sẵn
(``failure_category``) và test-kết-nối đã có ``error_code``. Gốc rễ là
``LLMError`` không mang mã nào, và ``_call_llm`` còn ném lại câu chung khi thử
hết các route, xoá luôn thứ vừa phân loại được.
"""
import time

import httpx
import pytest

from app.services.llm_client import (
    LLM_UNKNOWN_CODE_MESSAGE,
    LLM_USER_MESSAGES,
    LLMClient,
    LLMError,
    _http_status_code,
    _is_retryable,
    llm_user_message,
)
from app.services.ai_config import runtime_context


def route(name):
    return {"provider": "compatible", "provider_name": name, "model_name": name,
            "api_base": f"http://{name}.internal/v1", "temperature_default": .1,
            "config_id": name, "api_key": "secret-" + name}


# ---------------------------------------------------------------- mã lỗi --

def test_llm_error_carries_a_code():
    assert LLMError("boom", code="AUTH_FAILED").code == "AUTH_FAILED"


def test_llm_error_without_code_is_explicitly_unknown():
    """Chưa phân loại được thì nói là chưa, đừng giả vờ đã biết."""
    assert LLMError("boom").code is None


@pytest.mark.parametrize("status,expected", [
    (401, "AUTH_FAILED"), (403, "AUTH_FAILED"),
    (404, "NOT_FOUND"), (429, "RATE_LIMITED"),
    (500, "PROVIDER_ERROR"), (503, "PROVIDER_ERROR"),
    (400, "REQUEST_REJECTED"), (422, "REQUEST_REJECTED"),
])
def test_http_status_maps_to_the_right_action(status, expected):
    assert _http_status_code(status) == expected


def test_auth_and_rate_limit_are_not_the_same_error():
    """401 (khóa sai, HR không sửa được) khác 429 (chờ rồi bấm lại)."""
    assert _http_status_code(401) != _http_status_code(429)


# ------------------------------------------------------- thông báo cho HR --

def test_message_tells_hr_to_contact_admin_when_they_cannot_fix_it():
    for code in ("POLICY_BLOCKED", "AUTH_FAILED", "CONFIG_MISSING", "CONFIG_INVALID", "NOT_FOUND"):
        message, kind = llm_user_message(LLMError("x", code=code))
        assert kind == "admin", f"{code} phải nói báo Quản trị viên"
        assert "Quản trị viên" in message, f"{code} thiếu chỗ báo ai"


def test_message_tells_hr_to_retry_when_retrying_may_help():
    for code in ("RATE_LIMITED", "TIMEOUT", "INVALID_JSON", "PROVIDER_ERROR", "NETWORK_ERROR"):
        message, kind = llm_user_message(LLMError("x", code=code))
        assert kind == "retry", f"{code} phải nói thử lại"
        assert "thử lại" in message.lower(), f"{code} thiếu hướng dẫn thử lại"


def test_unknown_code_still_gives_something_actionable():
    message, kind = llm_user_message(LLMError("boom"))
    assert message == LLM_UNKNOWN_CODE_MESSAGE
    assert kind is None
    assert "thử lại" in message.lower()


def test_every_message_is_a_full_sentence_not_a_key():
    """Câu dài, có dấu câu — không phải khoá dịch 3 chữ."""
    for code, (message, kind) in LLM_USER_MESSAGES.items():
        assert len(message) > 40, f"{code} quá ngắn để hướng dẫn được"
        assert message.endswith("."), f"{code} thiếu dấu chấm cuối câu"
        assert kind in ("admin", "retry"), f"{code} có mức độ lạ: {kind}"


def test_technical_detail_is_never_the_user_message():
    """``str(exc)`` có thể chứa status HTTP và địa chỉ endpoint — chỉ vào log."""
    exc = LLMError("LLM API error: 401", code="AUTH_FAILED")
    message, _ = llm_user_message(exc)
    assert "401" not in message
    assert "LLM API error" not in message


# ------------------------------------------------------------ retry --

def test_config_and_policy_errors_are_not_retried():
    """Lỗi tất định: gọi lại y nguyên thì y nguyên. Retry chỉ bắt HR chờ."""
    for code in ("POLICY_BLOCKED", "CONFIG_MISSING", "CONFIG_INVALID", "AUTH_FAILED", "NOT_FOUND"):
        assert _is_retryable(LLMError("x", code=code)) is False, f"{code} không đáng retry"


def test_transient_errors_are_still_retried():
    for code in ("RATE_LIMITED", "TIMEOUT", "PROVIDER_ERROR", "NETWORK_ERROR", "INVALID_JSON", None):
        assert _is_retryable(LLMError("x", code=code)) is True, f"{code} đáng retry"


def test_http_errors_are_always_retried():
    assert _is_retryable(httpx.ConnectError("boom")) is True


# ------------------------------------------- mã lỗi không bị nuốt khi fallback --

@pytest.mark.asyncio
async def test_code_survives_the_fallback_chain(monkeypatch):
    """Thử hết các route thì mã của lần CUỐI phải còn.

    Đây chính là chỗ làm mất mã trước đây: ``_call_llm`` bắt ``LLMError`` để thử
    route kế tiếp, và khi hết route thì ném ``LLMError("All configured LLM routes
    failed")`` — không truyền ``code``. Phân loại đúng ở tầng dưới cũng vô ích.
    """
    client = LLMClient()

    async def fake_once(*args, **kwargs):
        raise LLMError("private-secret", code="AUTH_FAILED")

    monkeypatch.setattr(client, "_call_llm_one", fake_once)
    primary = route("primary")
    primary["fallbacks"] = [route("secondary")]
    token = runtime_context.set(primary)
    try:
        with pytest.raises(LLMError) as exc:
            await client._call_llm("system", "synthetic")
        assert exc.value.code == "AUTH_FAILED"
        # Câu chung vẫn không lộ chi tiết nhà cung cấp.
        assert "private-secret" not in str(exc.value)
        assert str(exc.value) == "All configured LLM routes failed"
    finally:
        runtime_context.reset(token)


@pytest.mark.asyncio
async def test_endpoint_policy_code_reaches_the_caller(monkeypatch):
    """Chốt chặn egress phải mang POLICY_BLOCKED ra tới API.

    Đây là lỗi HR gặp đầu tiên khi vừa deploy (chưa bật ALLOW_EXTERNAL_API), nên
    mã này là mã quan trọng nhất trong cả nhóm.
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_EXTERNAL_API", False)
    with pytest.raises(LLMError) as exc:
        LLMClient()._check_endpoint_policy("https://example.com/v1")
    assert exc.value.code == "POLICY_BLOCKED"
    assert llm_user_message(exc.value)[1] == "admin"


@pytest.mark.asyncio
async def test_policy_error_is_not_retried_end_to_end(monkeypatch):
    """Kiểm qua CHÍNH decorator, bằng thời gian chờ.

    Đếm số request KHÔNG phân biệt được: ``_check_endpoint_policy`` chặn trước
    khi mở kết nối nên số request luôn bằng 0 dù có retry hay không. Thứ khác
    biệt duy nhất là HR phải chờ backoff.

    Trước khi sửa: 3 lần thử, backoff 2+4 = ~4 giây, rồi vẫn nhận đúng lỗi
    tất định đó (đo thực tế: 4.02s). Sau khi sửa: một lần, 0.01s.
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_EXTERNAL_API", False)

    primary = {**route("primary"), "api_base": "https://blocked.example.com/v1"}
    token = runtime_context.set(primary)
    try:
        started = time.monotonic()
        with pytest.raises(LLMError) as exc:
            await LLMClient()._call_llm("system", "synthetic")
        elapsed = time.monotonic() - started
        assert exc.value.code == "POLICY_BLOCKED"
        # Backoff tối thiểu của lần thử 2 là 2 giây. Dưới 1 giây nghĩa là
        # không có lần thử thứ hai.
        assert elapsed < 1.0, f"lỗi chính sách bị retry: chờ {elapsed:.2f}s"
    finally:
        runtime_context.reset(token)


@pytest.mark.asyncio
async def test_transient_error_still_retries_end_to_end(monkeypatch):
    """Chiều ngược lại: lỗi mạng vẫn phải thử 3 lần."""
    from tenacity import wait_none
    attempts = []

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            attempts.append(url)
            raise httpx.ConnectError("network down")

    monkeypatch.setattr("app.services.llm_client.httpx.AsyncClient", Client)
    monkeypatch.setattr(LLMClient._call_llm_one.retry, "wait", wait_none())
    primary = {**route("primary"), "api_base": "http://127.0.0.1:11434/v1"}
    token = runtime_context.set(primary)
    try:
        with pytest.raises(LLMError) as exc:
            await LLMClient()._call_llm("system", "synthetic")
        assert len(attempts) == 3, f"phải thử 3 lần, thực tế {len(attempts)}"
        assert exc.value.code == "NETWORK_ERROR"
    finally:
        runtime_context.reset(token)
