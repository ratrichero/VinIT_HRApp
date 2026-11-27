from pydantic import BaseModel, Field, model_validator
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID
from enum import Enum
from .common import BaseSchema, TimestampMixin


class CriteriaCategory(str, Enum):
    MUST_HAVE = "MUST_HAVE"
    NICE_TO_HAVE = "NICE_TO_HAVE"


class CriterionRating(str, Enum):
    STRONG_MATCH = "STRONG_MATCH"
    MATCH = "MATCH"
    UNCLEAR = "UNCLEAR"
    NO_MATCH = "NO_MATCH"


class CriteriaStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_HR_REVIEW = "PENDING_HR_REVIEW"
    PENDING_HM_APPROVAL = "PENDING_HM_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RequirementSpec(BaseSchema):
    """Structured, HR-reviewable form of a criterion requirement.

    The deterministic engine can infer a draft spec from free text, but a
    spec stored on the criterion is the reviewed source of truth used at
    assessment time.
    """

    kind: Literal["SKILL", "YEARS", "DEGREE", "CERTIFICATION", "LANGUAGE"] = "SKILL"
    terms: List[str] = Field(default_factory=list, max_length=12)
    min_years: Optional[float] = Field(default=None, ge=0, le=80)
    required_degree_level: Optional[int] = Field(default=None, ge=1, le=5)
    required_languages: List[str] = Field(default_factory=list, max_length=10)
    required_ielts: Optional[float] = Field(default=None, ge=0, le=9)
    required_toeic: Optional[int] = Field(default=None, ge=0, le=990)
    required_cefr: Optional[Literal["A1", "A2", "B1", "B2", "C1", "C2"]] = None
    required_language_rank: Optional[int] = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def threshold_matches_kind(self):
        if self.kind == "YEARS" and self.min_years is None:
            raise ValueError("Tiêu chí số năm cần min_years")
        if self.kind == "DEGREE" and self.required_degree_level is None:
            raise ValueError("Tiêu chí bằng cấp cần required_degree_level")
        if self.kind == "LANGUAGE" and not (
            self.required_languages or self.required_ielts is not None
            or self.required_toeic is not None or self.required_cefr
            or self.required_language_rank is not None
        ):
            raise ValueError("Tiêu chí ngoại ngữ cần ngôn ngữ hoặc mức yêu cầu")
        if self.kind in ("SKILL", "CERTIFICATION") and not self.terms:
            raise ValueError("Tiêu chí kỹ năng/chứng chỉ cần ít nhất một thuật ngữ")
        return self


class CriterionBase(BaseSchema):
    name: str
    description: str
    category: CriteriaCategory
    weight_in_group: float = Field(..., ge=0, le=100, description="Weight percentage within its category group")
    expected_evidence_keywords: List[str] = Field(default_factory=list)
    requirement_spec: Optional[RequirementSpec] = None
    evidence_guidance: Optional[str] = None
    jd_reference_text: Optional[str] = None


class CriterionCreate(CriterionBase):
    pass


class CriterionUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[CriteriaCategory] = None
    weight_in_group: Optional[float] = Field(default=None, ge=0, le=100)
    expected_evidence_keywords: Optional[List[str]] = None
    requirement_spec: Optional[RequirementSpec] = None


class Criterion(CriterionBase, TimestampMixin):
    source_template_item_id: Optional[UUID] = None
    criterion_id: UUID
    criteria_version_id: UUID
    display_order: int
    #: Tiêu chí đã chọn loại nhưng **chưa có ngưỡng** (bậc bằng, số năm, mức
    #: ngoại ngữ). Đây là trạng thái hợp lệ của quy trình: HR chọn loại trước,
    #: điền ngưỡng sau. Trường này tồn tại để giao diện vẫn vẽ được ô ngưỡng và
    #: biết nó đang trống — thay vì nhận ``requirement_spec = null`` rồi đoán ra
    #: SKILL và **giấu mất ô cần điền**.
    #:
    #: ``requirement_spec`` đi kèm vẫn phải qua được schema (tức đã có ngưỡng
    #: hoặc đủ thuật ngữ), nên khi cờ này bật, spec trả về là bản đã điền sẵn
    #: giá trị hợp lệ để giao diện hiển thị; giá trị thật vẫn là "chưa có".
    threshold_pending: bool = False


class CriteriaVersionBase(BaseSchema):
    jd_version_id: UUID
    origin: str = Field(default="AI_DRAFT", description="AI_DRAFT or HR_CREATED")
    mandatory_weight_total: float = 70.0
    nice_to_have_weight_total: float = 30.0
    policy_version: Optional[str] = None


class CriteriaVersionCreate(CriteriaVersionBase):
    criteria: List[CriterionCreate]


class CriteriaWeightsUpdate(BaseSchema):
    # The groups are percentages stored in NUMERIC(5,2); keeping the sum in
    # Decimal prevents rounding a malformed rubric into an approved one.
    mandatory_weight_total: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    nice_to_have_weight_total: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)

    @model_validator(mode="after")
    def weights_total_100(self):
        if self.mandatory_weight_total + self.nice_to_have_weight_total != Decimal("100"):
            raise ValueError("Tổng trọng số hai nhóm phải bằng 100%")
        return self


class CriterionWeightUpdate(BaseSchema):
    criterion_id: UUID
    weight_in_group: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class CriteriaItemWeightsUpdate(BaseSchema):
    items: List[CriterionWeightUpdate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_criterion_ids(self):
        ids = [item.criterion_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Danh sách trọng số tiêu chí bị trùng")
        return self


class CriteriaVersion(CriteriaVersionBase, TimestampMixin):
    source_template_version_id: Optional[UUID] = None
    criteria_version_id: UUID
    position_id: UUID
    version_number: int
    status: CriteriaStatus
    approved_by_hr_at: Optional[datetime] = None
    approved_by_hm_at: Optional[datetime] = None
    approved_by_hr: Optional[UUID] = None
    approved_by_hm: Optional[UUID] = None
    criteria: List[Criterion] = Field(default_factory=list)


class GenerateCriteriaRequest(BaseSchema):
    position_id: UUID
    jd_content: str = Field(..., description="Job Description text for AI to extract criteria")


class ApprovalAction(str, Enum):
    APPROVE = "APPROVE"
    DIRECT_APPROVE = "DIRECT_APPROVE"
    REJECT = "REJECT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class CriteriaApprovalRequest(BaseSchema):
    action: ApprovalAction
    comment: Optional[str] = None
