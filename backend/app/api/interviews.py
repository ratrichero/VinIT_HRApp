"""Lịch phỏng vấn — buổi phỏng vấn và người tham gia.

Vì sao module này: hệ thống dừng ở sàng lọc. Trạng thái ``INTERVIEW`` có trong
ma trận chuyển trạng thái từ Phase 1, nhưng không có nơi nào ghi **một buổi**:
ai, khi nào, ở đâu, vòng mấy. "Hồ sơ đang ở vòng phỏng vấn" vì thế chỉ là một
nhãn; HR vẫn giữ lịch ở email/Excel rồi quay lại đổi trạng thái bằng tay.

Bốn quyết định (``doc/DE_XUAT_LICH_PHONG_VAN.md`` §1), đều đã chốt:

* **Ai tạo** (Q1): HR phụ trách vị trí và HR_LEAD. Hiring Manager **không** tạo
  được — HM chỉ thấy hồ sơ đã được share, nên cho HM đặt lịch là mở đường vòng
  qua bước shortlist.
* **Nhiều người một buổi** (Q2): có. Mỗi ``INTERVIEWER`` một scorecard; xem
  ``/interviews/{id}/scorecards``.
* **Vòng** (Q3): bắt buộc, 1..10.
* **Thông báo** (Q4): chưa gửi thư ở vòng này. Không có cột nào cho việc đó, để
  không ai tưởng đã gửi.

**Lịch là dữ liệu bổ sung.** Không có endpoint nào ở đây đổi trạng thái hồ sơ,
và không có chốt nào bắt buộc phải có lịch mới chuyển được trạng thái. Nếu biến
lịch thành điều kiện, mọi hồ sơ đang ``INTERVIEW`` sẽ thành dữ liệu không hợp lệ.

Múi giờ: nhận ISO-8601 **bắt buộc có offset**, lưu UTC, trả nguyên văn UTC kèm
``+00:00``. Giao diện tự hiện theo giờ máy người dùng.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.security import get_current_user
from app.core.exceptions import NotFoundError
from app.db.database import SessionLocal

router = APIRouter()

LOCATION_KINDS = ("ONSITE", "ONLINE", "PHONE")
STATUSES = ("SCHEDULED", "DONE", "CANCELLED", "NO_SHOW")


class ParticipantIn(BaseModel):
    user_id: UUID
    participant_role: str = Field(default="INTERVIEWER")

    @model_validator(mode="after")
    def valid_role(self):
        if self.participant_role not in ("INTERVIEWER", "OBSERVER"):
            raise ValueError("Vai trò chỉ có thể là INTERVIEWER hoặc OBSERVER")
        return self


class InterviewCreate(BaseModel):
    application_id: UUID
    round_number: int = Field(default=1, ge=1, le=10)
    starts_at: datetime
    ends_at: datetime
    location_kind: str
    location_text: str | None = Field(default=None, max_length=500)
    participants: list[ParticipantIn] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def check_times_and_location(self):
        # Không có offset thì không biết 14:00 là giờ nào. Chặn ở đây thay vì
        # đoán theo máy chủ — cùng khuôn với `application_deadline_at` ở
        # positions.py, để hai chỗ đặt thời gian có cùng một luật.
        for value, label in ((self.starts_at, "Bắt đầu"), (self.ends_at, "Kết thúc")):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} cần múi giờ rõ ràng")
        if self.ends_at <= self.starts_at:
            raise ValueError("Kết thúc phải sau bắt đầu")
        if self.location_kind not in LOCATION_KINDS:
            raise ValueError("Hình thức chỉ có thể là ONSITE, ONLINE hoặc PHONE")
        if self.location_kind != "ONSITE" and not (self.location_text or "").strip():
            raise ValueError("Hẹn online hoặc qua điện thoại cần link hoặc số liên hệ")
        return self


class InterviewUpdate(BaseModel):
    """Sửa lịch. Không cho đổi ``application_id`` — dời buổi sang hồ sơ khác là huỷ + tạo mới."""

    round_number: int | None = Field(default=None, ge=1, le=10)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location_kind: str | None = None
    location_text: str | None = Field(default=None, max_length=500)
    expected_updated_at: datetime | None = None


class ParticipantsReplace(BaseModel):
    """Thay toàn bộ người tham gia của một buổi **chưa diễn ra**.

    Vì sao là thay-toàn-bộ chứ không phải thêm/bớt từng người: người dùng sửa
    một danh sách, và danh sách đó là trạng thái cuối cùng họ thấy. Hai endpoint
    add/remove thì client phải tự tính hiệu, và hai client bấm cùng lúc sẽ ra
    kết quả phụ thuộc thứ tự.

    Danh sách rỗng bị chặn: một buổi không có người phỏng vấn thì không ai
    chấm, tức là buổi không thể kết thúc đúng cách. Muốn bỏ hết thì huỷ buổi.
    """

    participants: list[ParticipantIn] = Field(min_length=1, max_length=30)


class StatusChange(BaseModel):
    status: str

    @model_validator(mode="after")
    def valid(self):
        if self.status not in STATUSES:
            raise ValueError("Trạng thái không hợp lệ")
        return self


# ---------------------------------------------------------------------------
# Quyền
# ---------------------------------------------------------------------------

def _actor_position_access(db, actor: str, application_id: str) -> tuple[dict, bool]:
    """Trả (dòng hồ sơ, có phải HR phụ trách/HR_LEAD không).

    Cùng định nghĩa với ``core/permissions._application_access_flags``: ADMIN và
    HR_LEAD toàn cục, hoặc được gán HR_RECRUITER/HR_LEAD cho đúng vị trí đó.
    Không dùng lại hàm kia vì hàm đó 403 khi người xem không có quyền xem hồ sơ;
    ở đây cần biết cả hai trạng thái để xử lý người tham gia (observer/HM chỉ xem).
    """
    row = db.execute(text("""
        SELECT a.application_id, a.position_id, a.status AS application_status
        FROM app_private.applications a WHERE a.application_id = :app
    """), {"app": application_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ")
    is_hr = bool(db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                        WHERE ur.user_id = :actor AND ur.revoked_at IS NULL
                          AND ur.role_code IN ('ADMIN','HR_LEAD'))
            OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                        WHERE pa.user_id = :actor AND pa.position_id = :position
                          AND pa.revoked_at IS NULL
                          AND pa.position_role IN ('HR_RECRUITER','HR_LEAD'))
    """), {"actor": actor, "position": str(row["position_id"])}).scalar_one())
    return dict(row), is_hr


def _is_hr_for_position(db, actor: str, position_id: str) -> bool:
    """HR của vị trí? Chỉ câu quyền, không đọc lại hồ sơ.

    Tách khỏi ``_require_hr_write`` vì các route ghi đã có sẵn dòng buổi phỏng vấn
    (đọc kèm ``FOR UPDATE``). Gọi ``_actor_position_access`` ở đó là đọc lại đúng
    hồ sơ vừa đọc — 2 truy vấn thừa mỗi lần ghi, và tệ hơn: nó đọc **ngoài** khoá,
    nên câu trả lời có thể đến từ một trạng thái khác với dòng đang giữ.
    """
    return bool(db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                        WHERE ur.user_id = :actor AND ur.revoked_at IS NULL
                          AND ur.role_code IN ('ADMIN','HR_LEAD'))
            OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                        WHERE pa.user_id = :actor AND pa.position_id = :position
                          AND pa.revoked_at IS NULL
                          AND pa.position_role IN ('HR_RECRUITER','HR_LEAD'))
    """), {"actor": actor, "position": str(position_id)}).scalar_one())


def _require_hr_write(db, actor: str, application_id: str) -> dict:
    row, is_hr = _actor_position_access(db, actor, application_id)
    if not is_hr:
        raise HTTPException(403, "Chỉ HR phụ trách vị trí hoặc HR Lead được đặt lịch phỏng vấn")
    return row


def _require_active(db, actor: str) -> None:
    """Tài khoản còn hoạt động. Token còn hạn không có nghĩa là quyền còn."""
    status = db.execute(text(
        "SELECT account_status FROM app_private.user_profiles WHERE user_id = :actor FOR SHARE"
    ), {"actor": actor}).scalar_one_or_none()
    if status != "ACTIVE":
        raise HTTPException(403, "Tài khoản không hoạt động")


def _audit(db, actor, action, interview_id, position_id, metadata=None):
    db.execute(text("""
        INSERT INTO app_private.audit_events
            (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
        VALUES (:actor, :action, 'INTERVIEW', :id, :position, 'SUCCESS', CAST(:metadata AS jsonb))
    """), {"actor": actor, "action": action, "id": str(interview_id),
           "position": str(position_id), "metadata": json.dumps(metadata or {})})


# ---------------------------------------------------------------------------
# Thông báo trong ứng dụng
# ---------------------------------------------------------------------------

def _notify(db, *, interview_id: str, recipients: set[str], kind: str, actor: str,
            payload: dict | None = None) -> int:
    """Ghi thông báo cho những người cần biết. Trả số dòng đã tạo.

    Ba quyết định ở đây:

    * **Không tự báo cho người vừa thao tác.** Họ vừa bấm nút, đã biết chuyện gì
      xảy ra; thêm một dòng "bạn vừa đổi lịch" chỉ làm badge tăng mà không ai
      cần đọc.
    * **Người nhận do nơi gọi tự chọn**, không suy từ bảng người tham gia tại
      đây: khi bớt một người khỏi buổi, người đó phải nhận thông báo *trước khi*
      bị xoá khỏi `interview_participants`. Suy muộn sẽ mất đúng người cần biết.
    * **Không chép nội dung buổi.** `payload` chỉ nói cái gì đổi; màn hình mở
      buổi để đọc giờ/nơi hiện tại.
    """
    recipients = {str(user) for user in recipients if str(user) != str(actor)}
    if not recipients:
        return 0
    for user_id in sorted(recipients):
        db.execute(text("""
            INSERT INTO app_private.interview_notifications
                (user_id, interview_id, kind, actor_user_id, payload)
            VALUES (:user, :interview, :kind, :actor, CAST(:payload AS jsonb))
        """), {"user": user_id, "interview": str(interview_id), "kind": kind,
               "actor": str(actor), "payload": json.dumps(payload or {})})
    return len(recipients)


def _participant_ids(db, interview_id: str) -> set[str]:
    return {str(x) for x in db.execute(text(
        "SELECT user_id FROM app_private.interview_participants WHERE interview_id = :id"
    ), {"id": str(interview_id)}).scalars()}


def _conflicting_interviews(db, *, user_ids: list[str], starts_at, ends_at,
                            exclude_interview: str | None, exclude_application: str | None = None) -> list[dict]:
    """Buổi đang hiệu lực mà một trong những người này đã có, chồng giờ.

    Vì sao kiểm theo **người**, không theo phòng: hai người khác nhau họp hai
    phòng cùng lúc là bình thường; một người ở hai phòng cùng lúc là không thể.
    Hệ thống chưa quản lý phòng nên chỉ kiểm được chỗ chắc chắn sai.

    Buổi `CANCELLED`/`NO_SHOW` không tính — giờ đó của người ta đã trống lại.
    """
    if not user_ids:
        return []
    clauses = ["i.status IN ('SCHEDULED', 'DONE')",
               "i.starts_at < :ends_at", "i.ends_at > :starts_at",
               "ip.user_id = ANY(CAST(:users AS uuid[]))"]
    params = {"starts_at": starts_at, "ends_at": ends_at,
              "users": "{" + ",".join(user_ids) + "}"}
    if exclude_interview:
        clauses.append("i.interview_id <> :self")
        params["self"] = str(exclude_interview)
    if exclude_application:
        # Cùng một hồ sơ: hai vòng khác nhau vẫn có thể liền nhau, nhưng báo
        # "trùng" giữa hai vòng của cùng ứng viên là nhiễu — đó là cùng một
        # buổi theo nghĩa lịch của ứng viên.
        clauses.append("i.application_id <> :app")
        params["app"] = str(exclude_application)
    rows = db.execute(text(f"""
        SELECT DISTINCT i.interview_id, i.round_number, i.starts_at, i.ends_at
        FROM app_private.interviews i
        JOIN app_private.interview_participants ip ON ip.interview_id = i.interview_id
        WHERE {' AND '.join(clauses)}
        ORDER BY i.starts_at LIMIT 5
    """), params).mappings().all()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Đọc
# ---------------------------------------------------------------------------

_INTERVIEW_SELECT = """
    SELECT i.*, a.position_id, a.status AS application_status,
           p.position_code, p.title AS position_title,
           ai.display_name AS candidate_name,
           (SELECT count(*) FROM app_private.interview_participants ip
             WHERE ip.interview_id = i.interview_id) AS participant_count,
           (SELECT count(*) FROM app_private.shortlist_scorecards sc
             WHERE sc.interview_id = i.interview_id AND sc.status = 'SUBMITTED') AS submitted_scorecards,
           (SELECT count(*) FROM app_private.shortlist_scorecards sc
             WHERE sc.interview_id = i.interview_id) AS total_scorecards
    FROM app_private.interviews i
    JOIN app_private.applications a ON a.application_id = i.application_id
    JOIN app_private.positions p ON p.position_id = a.position_id
    LEFT JOIN app_private.application_identities ai ON ai.application_id = a.application_id
"""


def _detail(db, interview_id: str) -> dict:
    row = db.execute(text(_INTERVIEW_SELECT + " WHERE i.interview_id = :id"),
                     {"id": interview_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
    data = dict(row)
    data["participants"] = [dict(r) for r in db.execute(text("""
        SELECT ip.user_id, ip.participant_role, up.display_name, up.email
        FROM app_private.interview_participants ip
        LEFT JOIN app_private.user_profiles up ON up.user_id = ip.user_id
        WHERE ip.interview_id = :id ORDER BY ip.participant_role, ip.created_at
    """), {"id": interview_id}).mappings()]
    return data


@router.get("")
def list_interviews(position_id: UUID | None = None, application_id: UUID | None = None,
                    from_at: datetime | None = None,
                    to_at: datetime | None = None, mine: bool = Query(False),
                    user: dict = Depends(get_current_user)):
    """Danh sách buổi phỏng vấn trong một khoảng thời gian.

    Ba đường vào, và mỗi đường có mức quyền riêng — lịch phỏng vấn là thông tin
    về ứng viên nên không có đường nào trả về "tất cả":

    * ``position_id`` — phải là HR của vị trí đó (hoặc HR_LEAD/ADMIN).
    * ``application_id`` — lịch của một hồ sơ; quyền xét trên vị trí của hồ sơ đó.
    * ``mine=true`` — chỉ buổi mình là người tham gia; mọi tài khoản đang hoạt
      động đều dùng được, vì nó chỉ trả về lịch của chính họ.
    * **không tham số** — chỉ HR_LEAD/ADMIN, tức người vốn xem được mọi vị trí.
      Người khác nhận 403 kèm hướng dẫn dùng ``position_id`` hoặc ``mine``.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        clauses = ["1=1"]
        params: dict = {"actor": actor}
        # Chặn ở đây, KHÔNG chỉ trong nhánh `position_id`.
        #
        # Trước đây không có bước này: gọi `GET /interviews` không tham số thì
        # `clauses` vẫn là ["1=1"], nên bất kỳ tài khoản đang hoạt động — người
        # phỏng vấn, OBSERVER, HM — nhận tới 200 buổi của MỌI vị trí kèm
        # `candidate_name`. Docstring của hàm nói ngược lại điều đó, và
        # `get_interview` (một buổi) thì có kiểm tra — chỉ đường list là thiếu.
        #
        # `mine=true` là lịch của chính mình: được phép, và bộ lọc participant
        # bên dưới giới hạn đúng những buổi mình tham gia.
        if not mine and not position_id and not application_id:
            # Không lọc gì mà cũng không phải "lịch của tôi" thì chỉ HR toàn cục
            # được xem — người khác phải nêu position_id (và sẽ qua kiểm tra vị
            # trí bên dưới) hoặc dùng mine=true.
            privileged = db.execute(text("""
                SELECT EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                                WHERE ur.user_id = :actor AND ur.revoked_at IS NULL
                                  AND ur.role_code IN ('ADMIN','HR_LEAD'))
            """), {"actor": actor}).scalar_one()
            if not privileged:
                raise HTTPException(403, "Cần chọn vị trí, hoặc dùng mine=true để xem lịch của bạn")
        if application_id:
            # Lọc theo hồ sơ: đây là thứ màn chi tiết ứng viên cần. Trước đây nó
            # gọi `GET /interviews` rồi lọc ở client, kéo về tới 200 buổi của
            # mọi vị trí cho mỗi lần mở hồ sơ.
            owner = db.execute(text("""
                SELECT a.position_id FROM app_private.applications a
                WHERE a.application_id = :app
            """), {"app": str(application_id)}).mappings().first()
            if not owner:
                raise NotFoundError("Application")
            allowed_on_app = db.execute(text("""
                SELECT EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                                WHERE ur.user_id = :actor AND ur.revoked_at IS NULL
                                  AND ur.role_code IN ('ADMIN','HR_LEAD'))
                    OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                                WHERE pa.user_id = :actor AND pa.position_id = :position
                                  AND pa.revoked_at IS NULL
                                  AND pa.position_role IN ('HR_RECRUITER','HR_LEAD'))
            """), {"actor": actor, "position": str(owner["position_id"])}).scalar_one()
            if not allowed_on_app:
                raise HTTPException(403, "Không có quyền xem lịch của hồ sơ này")
            clauses.append("i.application_id = :application")
            params["application"] = str(application_id)

        if position_id:
            allowed = db.execute(text("""
                SELECT EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                                WHERE ur.user_id = :actor AND ur.revoked_at IS NULL
                                  AND ur.role_code IN ('ADMIN','HR_LEAD'))
                    OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                                WHERE pa.user_id = :actor AND pa.position_id = :position
                                  AND pa.revoked_at IS NULL
                                  AND pa.position_role IN ('HR_RECRUITER','HR_LEAD'))
            """), {"actor": actor, "position": str(position_id)}).scalar_one()
            if not allowed:
                raise HTTPException(403, "Không có quyền xem lịch của vị trí này")
            clauses.append("a.position_id = :position")
            params["position"] = str(position_id)
        if mine:
            clauses.append("""EXISTS (SELECT 1 FROM app_private.interview_participants ip
                                       WHERE ip.interview_id = i.interview_id
                                         AND ip.user_id = :actor)""")
        if from_at is not None:
            if from_at.tzinfo is None or from_at.utcoffset() is None:
                raise HTTPException(400, "Mốc thời gian cần múi giờ rõ ràng")
            clauses.append("i.starts_at >= :from_at")
            params["from_at"] = from_at
        if to_at is not None:
            if to_at.tzinfo is None or to_at.utcoffset() is None:
                raise HTTPException(400, "Mốc thời gian cần múi giờ rõ ràng")
            clauses.append("i.starts_at < :to_at")
            params["to_at"] = to_at
        rows = db.execute(text(_INTERVIEW_SELECT + " WHERE " + " AND ".join(clauses)
                              + " ORDER BY i.starts_at, i.interview_id LIMIT 200"),
                          params).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.get("/{interview_id}")
def get_interview(interview_id: UUID, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT a.application_id, a.position_id FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        _, is_hr = _actor_position_access(db, actor, str(row["application_id"]))
        is_participant = bool(db.execute(text("""
            SELECT EXISTS (SELECT 1 FROM app_private.interview_participants
                            WHERE interview_id = :id AND user_id = :actor)
        """), {"id": str(interview_id), "actor": actor}).scalar_one())
        if not is_hr and not is_participant:
            raise HTTPException(403, "Không có quyền xem buổi phỏng vấn này")
        return _detail(db, str(interview_id))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Ghi
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def create_interview(payload: InterviewCreate, user: dict = Depends(get_current_user)):
    """Tạo buổi phỏng vấn + người tham gia trong **một** transaction.

    Hai người tham gia và buổi phải cùng sống hoặc cùng chết: một buổi không có
    người phỏng vấn là buổi không ai chấm được, và sẽ nằm lại trong lịch như một
    lỗi không ai sửa.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        app_row = _require_hr_write(db, actor, str(payload.application_id))
        # Không đặt lịch được cho hồ sơ chưa qua sàng lọc. Nếu chặn ở đây quá
        # tay, HR sẽ thấy lỗi khi muốn mời phỏng vấn thẳng — nhưng cho phép là
        # bỏ qua bước shortlist, và mọi báo cáo "tỉ lệ qua sàng lọc" sai theo.
        if app_row["application_status"] not in ("SHORTLIST", "INTERVIEW", "OFFERED"):
            raise HTTPException(
                409, "Chỉ đặt lịch phỏng vấn cho hồ sơ đã qua sàng lọc (SHORTLIST trở lên)")

        # Người tham gia phải là người dùng đang hoạt động và có vai trò trên hệ
        # thống; thêm một người không tồn tại thì scorecard của họ không ai nộp.
        ids = sorted({str(p.user_id) for p in payload.participants})
        active = db.execute(text("""
            SELECT count(*) FROM app_private.user_profiles
            WHERE user_id = ANY(CAST(:ids AS uuid[])) AND account_status = 'ACTIVE'
        """), {"ids": "{" + ",".join(ids) + "}"}).scalar_one()
        if int(active) != len(ids):
            raise HTTPException(400, "Có người tham gia không tồn tại hoặc tài khoản đã đóng")

        # Chồng lấn: một người không thể ở hai buổi cùng lúc. Chặn ở đây thay vì
        # để người ta phát hiện lúc đã ngồi trong phòng. Cố ý là **409 kèm tên
        # các buổi trùng**, không phải 400 im lặng: người đặt cần biết trùng với
        # buổi nào để chọn giờ khác.
        conflicts = _conflicting_interviews(
            db, user_ids=ids, starts_at=payload.starts_at, ends_at=payload.ends_at,
            exclude_interview=None)
        if conflicts:
            first = conflicts[0]
            raise HTTPException(409,
                f"Người tham gia đã có buổi phỏng vấn trùng giờ (vòng {first['round_number']}, "
                f"{first['starts_at'].isoformat()}). Chọn giờ khác hoặc đổi người.")

        try:
            interview_id = db.execute(text("""
                INSERT INTO app_private.interviews
                    (application_id, round_number, starts_at, ends_at, location_kind, location_text, created_by)
                VALUES (:app, :round, :starts, :ends, :kind, :text, :actor)
                RETURNING interview_id
            """), {
                "app": str(payload.application_id), "round": payload.round_number,
                "starts": payload.starts_at, "ends": payload.ends_at,
                "kind": payload.location_kind,
                "text": (payload.location_text or "").strip() or None, "actor": actor,
            }).scalar_one()
        except IntegrityError:
            db.rollback()
            # Unique index bộ phận, không phải kiểm tra trước: hai HR bấm cùng lúc
            # thì DB mới là chỗ phân xử đúng.
            raise HTTPException(
                409, f"Hồ sơ đã có buổi phỏng vấn vòng {payload.round_number} đang hiệu lực") from None

        for participant in payload.participants:
            db.execute(text("""
                INSERT INTO app_private.interview_participants
                    (interview_id, user_id, participant_role, added_by)
                VALUES (:id, :user, :role, :actor)
                ON CONFLICT (interview_id, user_id) DO NOTHING
            """), {"id": str(interview_id), "user": str(participant.user_id),
                   "role": participant.participant_role, "actor": actor})

        # Báo cho những người vừa được gán: họ không bấm nút nào nên nếu im lặng
        # họ chỉ biết nếu tự mở lịch. Người vừa tạo thì không tự báo (xem _notify).
        _notify(db, interview_id=interview_id, recipients=set(ids),
                kind="INTERVIEW_CREATED", actor=actor,
                payload={"round_number": payload.round_number,
                         "starts_at": payload.starts_at.astimezone(timezone.utc).isoformat()})

        _audit(db, actor, "CREATE_INTERVIEW", interview_id, app_row["position_id"],
               {"round_number": payload.round_number,
                "participants": len(ids),
                "starts_at": payload.starts_at.astimezone(timezone.utc).isoformat()})
        result = _detail(db, str(interview_id))
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/{interview_id}")
def update_interview(interview_id: UUID, payload: InterviewUpdate,
                     user: dict = Depends(get_current_user)):
    """Sửa giờ/địa điểm/vòng. Không đổi được hồ sơ của buổi."""
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT i.interview_id, i.application_id, i.status, i.starts_at, i.ends_at,
                   i.round_number, i.updated_at, i.location_kind, i.location_text,
                   a.position_id
            FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id FOR UPDATE OF i
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        # Dòng đã khoá ở trên có sẵn position_id: kiểm quyền trực tiếp thay vì
        # đọc lại hồ sơ (xem _is_hr_for_position).
        if not _is_hr_for_position(db, actor, row["position_id"]):
            raise HTTPException(403, "Chỉ HR phụ trách vị trí hoặc HR Lead được thao tác trên lịch phỏng vấn")
        if row["status"] in ("DONE", "CANCELLED", "NO_SHOW"):
            raise HTTPException(409, "Buổi đã kết thúc hoặc đã huỷ, không sửa được nữa")
        # Optimistic lock: hai HR cùng mở form sửa thì người sau không ghi đè
        # lên thay đổi của người trước mà không biết.
        if payload.expected_updated_at is not None:
            if payload.expected_updated_at.astimezone(timezone.utc) != row["updated_at"].astimezone(timezone.utc):
                raise HTTPException(409, "Lịch đã được người khác thay đổi, tải lại trước khi sửa")

        values: dict = {}
        for field in ("round_number", "location_kind"):
            value = getattr(payload, field)
            if value is not None:
                values[field] = value
        if payload.location_kind is not None and payload.location_kind not in LOCATION_KINDS:
            raise HTTPException(400, "Hình thức không hợp lệ")
        if payload.location_text is not None:
            values["location_text"] = payload.location_text.strip() or None
        for field in ("starts_at", "ends_at"):
            value = getattr(payload, field)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise HTTPException(400, "Mốc thời gian cần múi giờ rõ ràng")
                values[field] = value
        if not values:
            raise HTTPException(400, "Không có nội dung cần cập nhật")

        starts = values.get("starts_at", row["starts_at"])
        ends = values.get("ends_at", row["ends_at"])
        if ends <= starts:
            raise HTTPException(400, "Kết thúc phải sau bắt đầu")
        # Đọc từ dòng đã khoá ở trên thay vì hai truy vấn phụ: cùng một dòng,
        # cùng transaction, và không có khe giữa hai lần đọc để người khác sửa.
        kind = values.get("location_kind", row["location_kind"])
        text_value = values.get("location_text", row["location_text"])
        if kind != "ONSITE" and not (text_value or "").strip():
            raise HTTPException(400, "Hẹn online hoặc qua điện thoại cần link hoặc số liên hệ")

        # Đổi giờ thì phải kiểm lại chồng lấn. Chỉ kiểm khi thời gian thật sự đổi:
        # sửa mỗi phòng họp không thể tạo ra trùng giờ, và báo lỗi trùng lúc đó là
        # chặn một việc vô hại.
        if "starts_at" in values or "ends_at" in values:
            conflicts = _conflicting_interviews(
                db, user_ids=sorted(_participant_ids(db, str(interview_id))),
                starts_at=starts, ends_at=ends, exclude_interview=str(interview_id),
                exclude_application=str(row["application_id"]))
            if conflicts:
                first = conflicts[0]
                raise HTTPException(409,
                    f"Người tham gia đã có buổi phỏng vấn trùng giờ (vòng {first['round_number']}, "
                    f"{first['starts_at'].isoformat()}). Chọn giờ khác.")

        sets = ", ".join(f"{key} = :{key}" for key in values)
        try:
            db.execute(text(f"""
                UPDATE app_private.interviews SET {sets}, updated_at = now()
                WHERE interview_id = :id
            """), {**values, "id": str(interview_id)})
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Vòng này đã có buổi khác đang hiệu lực") from None

        # Ai bị ảnh hưởng thì báo. Đổi giờ là loại thay đổi dễ làm người ta đi sai
        # giờ nhất, nên payload mang theo cả giờ cũ để câu thông báo nói được
        # "14:00 → 15:30" chứ không chỉ "đã đổi".
        _notify(db, interview_id=interview_id,
                recipients=_participant_ids(db, str(interview_id)),
                kind="INTERVIEW_UPDATED", actor=actor,
                payload={"fields": sorted(values),
                         "starts_at_from": row["starts_at"].astimezone(timezone.utc).isoformat(),
                         "starts_at_to": starts.astimezone(timezone.utc).isoformat()})

        _audit(db, actor, "UPDATE_INTERVIEW", interview_id, row["position_id"],
               {"fields": sorted(values)})
        result = _detail(db, str(interview_id))
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.put("/{interview_id}/participants")
def replace_participants(interview_id: UUID, payload: ParticipantsReplace,
                         user: dict = Depends(get_current_user)):
    """Đặt lại danh sách người phỏng vấn của buổi **chưa diễn ra**.

    Vì sao cần: trước endpoint này, tình huống thường gặp nhất — sáng mai phỏng
    vấn, một người báo ốm — chỉ có một cách là **huỷ buổi rồi tạo lại**. Cách đó
    xoá mất lịch sử "buổi này đã từng có ai", và nếu buổi đang ``DONE`` thì không
    tạo lại được cùng vòng (unique index chỉ miễn CANCELLED/NO_SHOW).

    Ba chốt:
    * Chỉ buổi ``SCHEDULED``. Buổi đã diễn ra thì danh sách người là **sự thật
      lịch sử** — scorecard của họ đã tồn tại, sửa danh sách sẽ làm scorecard mồ
      côi khỏi người được phân công.
    * Không cho bỏ người **đã có scorecard**: phiếu của họ đã gắn với buổi, xoá
      người không xoá phiếu, và người đó mất quyền đọc chính phiếu mình đã viết.
      Trả 409 và nói rõ tên.
    * Người bị bỏ **vẫn nhận thông báo** — họ cần biết mình không còn dự buổi.
      Đó là lý do `_notify` nhận danh sách người do nơi gọi chọn, không tự suy.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT i.interview_id, i.application_id, i.status, a.position_id
            FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id FOR UPDATE OF i
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        # Dòng đã khoá ở trên có sẵn position_id: kiểm quyền trực tiếp thay vì
        # đọc lại hồ sơ (xem _is_hr_for_position).
        if not _is_hr_for_position(db, actor, row["position_id"]):
            raise HTTPException(403, "Chỉ HR phụ trách vị trí hoặc HR Lead được thao tác trên lịch phỏng vấn")
        if row["status"] != "SCHEDULED":
            raise HTTPException(409, "Chỉ đổi người tham gia của buổi chưa diễn ra")

        ids = sorted({str(p.user_id) for p in payload.participants})
        roles = {str(p.user_id): p.participant_role for p in payload.participants}
        active = db.execute(text("""
            SELECT count(*) FROM app_private.user_profiles
            WHERE user_id = ANY(CAST(:ids AS uuid[])) AND account_status = 'ACTIVE'
        """), {"ids": "{" + ",".join(ids) + "}"}).scalar_one()
        if int(active) != len(ids):
            raise HTTPException(400, "Có người tham gia không tồn tại hoặc tài khoản đã đóng")

        before = _participant_ids(db, str(interview_id))
        removed = before - set(ids)
        added = set(ids) - before
        if removed:
            # Phiếu đã tồn tại thì người đó không thể bị bỏ: xoá người không xoá
            # phiếu, và họ mất quyền đọc chính đánh giá mình đã viết.
            with_cards = {str(x) for x in db.execute(text("""
                SELECT reviewer_user_id FROM app_private.shortlist_scorecards
                WHERE interview_id = :id AND reviewer_user_id = ANY(CAST(:users AS uuid[]))
            """), {"id": str(interview_id),
                   "users": "{" + ",".join(sorted(removed)) + "}"}).scalars()}
            if with_cards:
                names = db.execute(text("""
                    SELECT display_name FROM app_private.user_profiles
                    WHERE user_id = ANY(CAST(:users AS uuid[]))
                """), {"users": "{" + ",".join(sorted(with_cards)) + "}"}).scalars().all()
                shown = ", ".join(n for n in names if n) or f"{len(with_cards)} người"
                raise HTTPException(
                    409, f"Không bỏ được người đã có phiếu chấm điểm: {shown}")

        if removed:
            db.execute(text("""
                DELETE FROM app_private.interview_participants
                WHERE interview_id = :id AND user_id = ANY(CAST(:users AS uuid[]))
            """), {"id": str(interview_id), "users": "{" + ",".join(sorted(removed)) + "}"})
        for user_id in ids:
            # ON CONFLICT để đổi vai trò của người đã có (INTERVIEWER ↔ OBSERVER)
            # mà không phải xoá rồi thêm lại — xoá/thêm sẽ mất `created_at`, tức
            # là thứ tự người trong danh sách nhảy lung tung sau mỗi lần sửa.
            db.execute(text("""
                INSERT INTO app_private.interview_participants
                    (interview_id, user_id, participant_role, added_by)
                VALUES (:id, :user, :role, :actor)
                ON CONFLICT (interview_id, user_id)
                DO UPDATE SET participant_role = EXCLUDED.participant_role
            """), {"id": str(interview_id), "user": user_id,
                   "role": roles[user_id], "actor": actor})

        changed = added | removed
        if changed:
            # Báo cả người mới (cần biết có buổi) lẫn người bị bỏ (cần biết không
            # còn dự) — hai nhóm này ngược nhau nên không gộp vào một câu được.
            _notify(db, interview_id=str(interview_id), recipients=changed,
                    kind="PARTICIPANTS_CHANGED", actor=actor,
                    payload={"added": len(added), "removed": len(removed)})
        _audit(db, actor, "REPLACE_INTERVIEW_PARTICIPANTS", interview_id, row["position_id"],
               {"added": len(added), "removed": len(removed)})
        result = _detail(db, str(interview_id))
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


_CANCELLABLE_FROM = {"SCHEDULED": {"DONE", "CANCELLED", "NO_SHOW"},
                     "DONE": set(), "CANCELLED": set(), "NO_SHOW": set()}


@router.post("/{interview_id}/status")
def change_status(interview_id: UUID, payload: StatusChange,
                  user: dict = Depends(get_current_user)):
    """Chuyển trạng thái buổi: ``SCHEDULED → DONE / CANCELLED / NO_SHOW``.

    Cố ý **một chiều**. Mở lại buổi đã huỷ là tạo buổi mới cùng vòng (unique
    index bộ phận cho phép, vì buổi cũ đã ``CANCELLED``), để lịch sử nói đúng
    "đã huỷ rồi xếp lại" thay vì che mất lần huỷ.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT i.interview_id, i.application_id, i.status, a.position_id
            FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id FOR UPDATE OF i
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        # Dòng đã khoá ở trên có sẵn position_id: kiểm quyền trực tiếp thay vì
        # đọc lại hồ sơ (xem _is_hr_for_position).
        if not _is_hr_for_position(db, actor, row["position_id"]):
            raise HTTPException(403, "Chỉ HR phụ trách vị trí hoặc HR Lead được thao tác trên lịch phỏng vấn")
        if payload.status == row["status"]:
            # Idempotent: bấm hai lần không phải lỗi, nhưng cũng không ghi audit lần hai.
            return _detail(db, str(interview_id))
        if payload.status not in _CANCELLABLE_FROM[row["status"]]:
            raise HTTPException(
                409, f"Không chuyển được từ {row['status']} sang {payload.status}")
        db.execute(text("""
            UPDATE app_private.interviews SET status = :status, updated_at = now()
            WHERE interview_id = :id
        """), {"status": payload.status, "id": str(interview_id)})
        _audit(db, actor, "CHANGE_INTERVIEW_STATUS", interview_id, row["position_id"],
               {"from": row["status"], "to": payload.status})
        result = _detail(db, str(interview_id))
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Scorecard theo buổi (B2)
# ---------------------------------------------------------------------------

@router.post("/{interview_id}/scorecards", status_code=201)
def create_scorecards(interview_id: UUID, user: dict = Depends(get_current_user)):
    """Sinh scorecard cho từng người phỏng vấn của buổi, từ rubric đã duyệt.

    Ba điều cố ý:

    * **Chỉ sinh khi buổi đã ``DONE``.** Chấm trước khi phỏng vấn là chấm dự
      đoán; và nếu sinh sớm, người chấm mở ra thấy ô điểm cho một buổi chưa xảy
      ra — họ sẽ điền, và dữ liệu đó không phản ánh buổi nào cả.
    * **Rubric lấy theo đúng ``jd_version_id`` mới nhất của vị trí**, cùng định
      nghĩa với `/careers` và `criteria.py`. Nếu rubric đổi giữa lúc đặt lịch và
      lúc chấm, scorecard vẫn gắn bản rubric tại thời điểm sinh — không tự đổi
      tiêu chí dưới chân người chấm.
    * **Gọi lại không tạo bản trùng.** Unique index `(interview_id, reviewer)`
      chặn ở DB, và ở đây lọc người đã có scorecard trước khi chèn.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT i.interview_id, i.status, i.application_id, a.position_id,
                   a.status AS application_status
            FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id FOR UPDATE OF i
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        # Dòng đã khoá ở trên có sẵn position_id: kiểm quyền trực tiếp thay vì
        # đọc lại hồ sơ (xem _is_hr_for_position).
        if not _is_hr_for_position(db, actor, row["position_id"]):
            raise HTTPException(403, "Chỉ HR phụ trách vị trí hoặc HR Lead được thao tác trên lịch phỏng vấn")
        if row["status"] != "DONE":
            raise HTTPException(409, "Chỉ chấm điểm sau khi buổi phỏng vấn đã diễn ra (trạng thái DONE)")

        criteria_version = db.execute(text("""
            SELECT c.criteria_version_id FROM app_private.criteria_versions c
            WHERE c.position_id = :position AND c.status = 'APPROVED'
              AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                                      WHERE position_id = :position
                                      ORDER BY version_number DESC LIMIT 1)
            ORDER BY c.version_number DESC LIMIT 1
        """), {"position": str(row["position_id"])}).scalar_one_or_none()
        if not criteria_version:
            raise HTTPException(409, "Vị trí chưa có bộ tiêu chí được duyệt cho JD hiện tại")

        # Chỉ INTERVIEWER chấm; OBSERVER dự buổi để nghe, không cho điểm.
        reviewer_ids = [str(x) for x in db.execute(text("""
            SELECT ip.user_id FROM app_private.interview_participants ip
            WHERE ip.interview_id = :id AND ip.participant_role = 'INTERVIEWER'
              AND NOT EXISTS (SELECT 1 FROM app_private.shortlist_scorecards sc
                               WHERE sc.interview_id = :id AND sc.reviewer_user_id = ip.user_id)
            ORDER BY ip.created_at
        """), {"id": str(interview_id)}).scalars().all()]
        if not reviewer_ids:
            raise HTTPException(409, "Không còn người phỏng vấn nào cần tạo scorecard")

        due_at = datetime.now(timezone.utc) + timedelta(days=3)
        created = 0
        for reviewer in reviewer_ids:
            card_id = db.execute(text("""
                INSERT INTO app_private.shortlist_scorecards
                    (share_item_id, interview_id, reviewer_user_id, criteria_version_id, due_at)
                VALUES (NULL, :interview, :reviewer, :criteria, :due)
                RETURNING scorecard_id
            """), {"interview": str(interview_id), "reviewer": reviewer,
                   "criteria": str(criteria_version), "due": due_at}).scalar_one()
            db.execute(text("""
                INSERT INTO app_private.shortlist_scorecard_criteria(scorecard_id, criterion_id)
                SELECT :card, ci.criterion_id FROM app_private.criteria_items ci
                WHERE ci.criteria_version_id = :criteria
            """), {"card": card_id, "criteria": str(criteria_version)})
            created += 1

        _audit(db, actor, "CREATE_INTERVIEW_SCORECARDS", interview_id, row["position_id"],
               {"reviewers": created, "criteria_version_id": str(criteria_version)})
        db.commit()
        return {"interview_id": str(interview_id), "created": created,
                "criteria_version_id": str(criteria_version)}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/{interview_id}/scorecards")
def list_scorecards(interview_id: UUID, user: dict = Depends(get_current_user)):
    """Danh sách scorecard của buổi, kèm trạng thái nộp của từng người.

    HR xem được tất cả (để biết ai chưa nộp); người phỏng vấn chỉ thấy của mình.
    """
    db = SessionLocal()
    try:
        actor = user["user_id"]
        _require_active(db, actor)
        row = db.execute(text("""
            SELECT i.application_id, a.position_id FROM app_private.interviews i
            JOIN app_private.applications a ON a.application_id = i.application_id
            WHERE i.interview_id = :id
        """), {"id": str(interview_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy buổi phỏng vấn")
        _, is_hr = _actor_position_access(db, actor, str(row["application_id"]))
        is_participant = bool(db.execute(text("""
            SELECT EXISTS (SELECT 1 FROM app_private.interview_participants
                            WHERE interview_id = :id AND user_id = :actor)
        """), {"id": str(interview_id), "actor": actor}).scalar_one())
        if not is_hr and not is_participant:
            raise HTTPException(403, "Không có quyền xem scorecard của buổi này")
        return [dict(r) for r in db.execute(text("""
            SELECT sc.scorecard_id, sc.reviewer_user_id, sc.status, sc.due_at,
                   sc.submitted_at, sc.revision, sc.overall_recommendation,
                   up.display_name AS reviewer_name
            FROM app_private.shortlist_scorecards sc
            LEFT JOIN app_private.user_profiles up ON up.user_id = sc.reviewer_user_id
            WHERE sc.interview_id = :id
              AND (:see_all OR sc.reviewer_user_id = :actor)
            ORDER BY sc.created_at, sc.scorecard_id
        """), {"id": str(interview_id), "see_all": is_hr, "actor": actor}).mappings()]
    finally:
        db.close()
