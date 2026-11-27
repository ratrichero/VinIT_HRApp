"""Prompt sinh tiêu chí phải coi JD tiếng Việt là mặc định, không phải ngoại lệ.

Vì sao có tệp này: prompt cũ mở đầu bằng

    "The JD is expected to be in English and most JDs will be English.
     Vietnamese JDs are supported as an option, not as the default"

với một trường đại học Việt Nam thì đó là giả định ngược. Hậu quả không nhìn
thấy ngay — model vẫn chạy, vẫn trả JSON hợp lệ — nhưng nó có xu hướng dịch
nội dung sang tiếng Anh rồi mới sinh tiêu chí, và tiêu chí tiếng Anh đem đi
so khớp với CV tiếng Việt thì trượt từ khoá bằng chứng.

Cùng loại lỗi với `lang='eng'` gắn cứng của OCR: sai âm thầm, phát hiện muộn,
và sửa về sau phải làm lại dữ liệu đã sinh.

Trước tệp này không có test nào đọc nội dung prompt — đổi prompt thành gì cũng
không có gì đỏ.
"""
import pytest

from app.services.llm_client import LLMClient


async def _capture_prompt(monkeypatch, jd_text: str) -> dict:
    """Chạy ``extract_criteria_from_jd`` với ``_call_llm`` giả, trả prompt đã gửi."""
    captured: dict = {}

    async def fake_call(self, *, system_prompt, user_prompt, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return {
            "requisition_id": "REQ-1",
            "job_title": "Kỹ sư Backend",
            "criteria": [
                {"name": "Kinh nghiệm Python", "description": "Tối thiểu 4 năm",
                 "category": "MUST_HAVE", "weight": 100,
                 "expected_evidence_keywords": ["Python"]},
            ],
        }

    monkeypatch.setattr(LLMClient, "_call_llm", fake_call)
    await LLMClient().extract_criteria_from_jd(
        jd_text=jd_text, requisition_id="REQ-1", job_title="Kỹ sư Backend")
    return captured


@pytest.mark.asyncio
async def test_prompt_treats_vietnamese_as_the_default(monkeypatch):
    """Vietnamese phải là kỳ vọng mặc định, không phải tuỳ chọn."""
    prompt = (await _capture_prompt(monkeypatch, "Yêu cầu 4 năm kinh nghiệm Python."))["system_prompt"]
    assert "Vietnamese is the default expectation" in prompt
    # Câu cũ tuyệt đối không được quay lại: nó nói phần lớn JD là tiếng Anh.
    assert "most JDs will be English" not in prompt
    assert "not as the default" not in prompt


@pytest.mark.asyncio
async def test_prompt_still_handles_english_jd(monkeypatch):
    """Mặc định tiếng Việt không được biến thành chỉ-đọc-được-tiếng-Việt."""
    prompt = (await _capture_prompt(monkeypatch, "Requires 4 years of Python experience."))["system_prompt"]
    assert "English" in prompt
    assert "keep all output text in English" in prompt


@pytest.mark.asyncio
async def test_prompt_forbids_translating_the_enum_values(monkeypatch):
    """Nhãn nhóm phải giữ nguyên tiếng Anh dù JD tiếng Việt.

    ``coerce_category`` có alias tiếng Việt nên "Bắt buộc" vẫn về đúng nhóm —
    nhưng đó là lưới an toàn, không phải đường chính. Prompt phải nói rõ.
    """
    prompt = (await _capture_prompt(monkeypatch, "Yêu cầu 4 năm kinh nghiệm Python."))["system_prompt"]
    assert "Never translate these two values" in prompt
    assert "MUST_HAVE" in prompt and "NICE_TO_HAVE" in prompt


@pytest.mark.asyncio
async def test_prompt_forbids_discriminatory_criteria(monkeypatch):
    """Chốt chặn nội dung phân biệt đối xử — không được mất khi sửa prompt."""
    prompt = (await _capture_prompt(monkeypatch, "Yêu cầu 4 năm kinh nghiệm Python."))["system_prompt"]
    for forbidden in ("age", "gender", "marital status", "nationality", "appearance"):
        assert forbidden in prompt, f"prompt mất chốt chặn: {forbidden}"


@pytest.mark.asyncio
async def test_jd_text_is_wrapped_as_untrusted(monkeypatch):
    """JD là dữ liệu không tin cậy, không được chèn thẳng thành chỉ dẫn."""
    captured = await _capture_prompt(monkeypatch, "Yêu cầu 4 năm kinh nghiệm Python.")
    assert "untrusted_job_description" in captured["user_prompt"]


def test_prompt_version_was_bumped():
    """Đổi prompt mà không đổi version thì log không phân biệt được bộ cũ/mới."""
    from app.core.config import settings
    assert settings.CRITERIA_PROMPT_VERSION == "criteria-prompt-v2.2"
