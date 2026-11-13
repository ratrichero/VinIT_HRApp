from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum
from .common import BaseSchema, TimestampMixin


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class PositionRole(str, Enum):
    HR_RECRUITER = "HR_RECRUITER"
    HIRING_MANAGER = "HIRING_MANAGER"
    HR_LEAD = "HR_LEAD"
    VIEWER = "VIEWER"


class PositionBase(BaseSchema):
    position_code: str = Field(..., description="Unique position code, e.g. REQ-IT-001")
    title: str
    job_family: Optional[str] = None  # e.g. Software Engineering, QA
    org_unit: Optional[str] = None
    level: Optional[str] = None  # e.g. Junior, Mid, Senior
    work_location: Optional[str] = None
    work_mode: Optional[str] = None  # Remote, Hybrid, On-site
    employment_type: Optional[str] = None  # Full-time, Contract, etc.
    headcount: Optional[int] = Field(default=1, ge=1)


class PositionCreate(PositionBase):
    # New positions choose a department; the backend generates position_code
    # from that department's code_format (for example REQ-IT-001).
    department_id: UUID
    position_code: Optional[str] = Field(default=None, max_length=100)  # Deprecated: ignored, generated server-side
    org_unit: Optional[str] = Field(default=None, max_length=255)  # Deprecated: snapshot comes from the department
    jd_content: str = Field(..., description="Job Description text content in English")
    hiring_manager_user_id: Optional[UUID] = Field(
        None,
        description="User ID of the Hiring Manager responsible for this position (will auto-assign HIRING_MANAGER role)"
    )


class PositionUpdate(BaseSchema):
    title: Optional[str] = None
    status: Optional[PositionStatus] = None
    work_location: Optional[str] = None
    work_mode: Optional[str] = None


class HiringManagerChange(BaseModel):
    hiring_manager_user_id: UUID
    expected_assignments: List[str] = Field(max_length=100)


class Position(PositionBase, TimestampMixin):
    position_id: UUID
    department_id: Optional[UUID] = None
    department_name: Optional[str] = None
    department_code_format: Optional[str] = None
    department_sequence: Optional[int] = None
    status: PositionStatus
    created_by: UUID
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class PositionWithStats(Position):
    total_applications: int = 0
    new_applications: int = 0
    in_review: int = 0
    shortlisted: int = 0
    criteria_approved: bool = False
    criteria_status: Optional[str] = None  # Latest version, which can be newer than the approved version.


class JDVersionCreate(BaseModel):
    content_text: str = Field(min_length=1, max_length=100_000)
    language_code: str = Field(default="vi", pattern="^(vi|en)$")
    expected_jd_version_id: UUID
