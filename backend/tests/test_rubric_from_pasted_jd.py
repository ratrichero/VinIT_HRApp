"""Sinh nháp rubric từ JD dán tay, và một bộ tiêu chí hiệu lực mỗi vị trí.

Hai thay đổi đi cùng nhau vì cùng một lý do: HR cần dựng rubric mẫu *trước* khi
mở vị trí, và khi đã có rubric mẫu thì vị trí không được phép giữ hai bộ tiêu
chí cùng hiệu lực.

Test ở đây đọc mã nguồn thay vì dựng DB: mọi chốt chặn đều là truy vấn SQL, và
một thay đổi làm mất chốt sẽ không kéo theo test nào khác đỏ.
"""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RUBRICS = (BACKEND / "app" / "api" / "rubric_library.py").read_text()
CRITERIA = (BACKEND / "app" / "api" / "criteria.py").read_text()
MIGRATION = (BACKEND.parent / "supabase" / "migrations" / "00037_criteria_superseded_status.sql").read_text()

SHARED_START = RUBRICS.index("async def _draft_from_jd_text")
SHARED_END = RUBRICS.index("@router.post('/suggest-from-position')")
SHARED = RUBRICS[SHARED_START:SHARED_END]

JD_START = RUBRICS.index("async def suggest_from_jd_text")
JD_BODY = RUBRICS[JD_START:]


# ---------------------------------------------------------------------------
# Sinh nháp từ JD dán tay
# ---------------------------------------------------------------------------


def test_pasted_jd_endpoint_writes_nothing():
    """Dán JD để lấy nháp — không được tạo vị trí, không được tạo JD.

    Nếu endpoint này ghi ``jd_versions``, mỗi lần HR thử một JD sẽ để lại một
    dòng rác gắn với một vị trí không tồn tại. Nháp phải là nháp.
    """
    for keyword in ("INSERT INTO", "UPDATE app_private", "DELETE FROM"):
        assert keyword not in JD_BODY, f"suggest-from-jd không được chứa {keyword}"


def test_pasted_jd_requires_a_family():
    """Rubric không nhóm thì không tái sử dụng được, mất nghĩa của thư viện."""
    assert "job_families WHERE job_family_id=:id" in JD_BODY
    assert "404" in JD_BODY


def test_pasted_jd_does_not_reuse_a_real_position_code():
    """Mã yêu cầu giả phải trông là giả, không được bịa mã như vị trí thật."""
    assert "PASTED-JD" in JD_BODY


def test_both_suggestion_paths_share_one_implementation():
    """Hai đường sinh nháp phải dùng chung một chỗ kiểm output.

    Lý do: model trả về cùng những kiểu sai (nhãn tiếng Việt, trọng số dạng
    chuỗi) ở cả hai đường. Tách làm hai bản sao thì sửa một bên là bên kia
    lặng lẽ khác đi.
    """
    assert RUBRICS.count("async def _draft_from_jd_text") == 1
    position_body = RUBRICS[RUBRICS.index("async def suggest_from_position"):JD_START]
    assert "_draft_from_jd_text(" in position_body
    assert "_draft_from_jd_text(" in JD_BODY
    # Không được tự gọi model trực tiếp ở một trong hai đường.
    assert "extract_criteria_from_jd" not in position_body
    assert "extract_criteria_from_jd" not in JD_BODY


def test_shared_draft_keeps_per_item_rejection_without_losing_the_batch():
    """Một tiêu chí hỏng không được làm hỏng cả bộ — nhưng phải đếm để báo lại."""
    assert "rejected += 1" in SHARED
    assert "return normalize_weights_in_group(items), rejected" in SHARED


def test_shared_draft_rejects_an_empty_batch():
    """Toàn bộ tiêu chí hỏng thì phải 502, không được trả danh sách rỗng."""
    assert "if not items:" in SHARED
    assert "502" in SHARED


def test_weights_are_normalised_to_100_per_group():
    assert "normalize_weights_in_group(items)" in SHARED


# ---------------------------------------------------------------------------
# Một bộ tiêu chí hiệu lực mỗi vị trí
# ---------------------------------------------------------------------------


def test_approving_a_version_supersedes_the_previous_one():
    """Không hạ bộ cũ thì vị trí có hai bộ APPROVED cho cùng một JD."""
    approve = CRITERIA[CRITERIA.index("new_status, reviewer_role = criteria_decision"):]
    approve = approve[: approve.index("updated = dict(")]
    assert "SET status = 'SUPERSEDED'" in approve
    assert "AND status = 'APPROVED'" in approve
    assert "criteria_version_id <> :cv_id" in approve, "phải loại trừ chính bộ đang duyệt"


def test_supersede_is_audited_with_the_replacement():
    """Truy được: bộ cũ nào, ai thay, bằng bộ nào."""
    assert "SUPERSEDE_CRITERIA_VERSION" in CRITERIA
    for field in ("superseded_by", "superseded_by_version", "version_number"):
        assert f'"{field}"' in CRITERIA


def test_supersede_happens_before_the_new_status_is_written():
    """Thứ tự quan trọng: hạ bộ cũ TRƯỚC khi ghi APPROVED cho bộ mới.

    Ngược lại thì có một khoảnh khắc hai bộ cùng APPROVED, và một request đọc
    xen vào giữa sẽ chọn sai bộ.
    """
    approve = CRITERIA[CRITERIA.index("new_status, reviewer_role = criteria_decision"):]
    supersede_at = approve.index("SET status = 'SUPERSEDED'")
    write_at = approve.index("SET status = :new_status")
    assert supersede_at < write_at


def test_superseded_is_a_distinct_status_not_an_alias():
    """Bộ bị thay thế KHÔNG được gộp vào nhãn "bị loại".

    Nó vẫn là bằng chứng đã duyệt và đã chấm ứng viên cũ. Gộp vào ARCHIVED
    nghĩa là sau này không phân biệt được "bộ này bị bỏ vì sai" với "bộ này
    đúng nhưng đã có bộ mới hơn".

    REJECTED vẫn phải còn trong constraint — đó là trạng thái có thật khi
    người duyệt từ chối một bộ.
    """
    constraint = MIGRATION.split("CHECK (status IN (")[1].split(")")[0]
    assert "SUPERSEDED" in constraint
    assert "REJECTED" in constraint, "REJECTED là trạng thái thật, không được làm mất"
    assert "APPROVED" in constraint
    assert "ARCHIVED" not in constraint, "criteria_versions không dùng ARCHIVED — đừng thêm vào"


def test_migration_is_idempotent():
    """Chạy lại phải không hỏng: repo này áp migration tay trên DB thật."""
    assert "DROP CONSTRAINT IF EXISTS" in MIGRATION
    assert "ADD CONSTRAINT" in MIGRATION
    assert "CREATE INDEX IF NOT EXISTS" in MIGRATION


def test_migration_does_not_touch_data():
    """Chỉ nới ràng buộc, không được UPDATE dữ liệu đang có."""
    assert "UPDATE " not in MIGRATION
    assert "DELETE " not in MIGRATION
    assert "INSERT " not in MIGRATION


# ---------------------------------------------------------------------------
# Nháp rubric trong trình duyệt: chống mất dữ liệu, nhưng không giữ quá lâu
# ---------------------------------------------------------------------------

RUBRIC_PAGE = (BACKEND.parent / "frontend" / "src" / "app" / "rubrics" / "page.tsx").read_text()
DRAFTS = (BACKEND.parent / "frontend" / "src" / "lib" / "localDrafts.ts").read_text()


def test_leaving_the_page_with_unsaved_rubric_asks_first():
    """Sinh nháp bằng AI mất hàng chục giây; đóng tab ngang là mất trắng."""
    assert "useUnsavedChangesGuard(dirty" in RUBRIC_PAGE


def test_draft_survives_a_hard_close():
    """Hộp thoại beforeunload không phải lúc nào cũng hiện, nên phải có lưu tạm."""
    assert "writeDraft(rubricDraftKey()" in RUBRIC_PAGE
    assert "readDraft<any>(rubricDraftKey())" in RUBRIC_PAGE


def test_one_draft_key_not_one_per_version():
    """Một khoá duy nhất: HR chỉ soạn một bản tại một thời điểm.

    Tách khoá theo phiên bản thì có thể tồn tại hai nháp cùng lúc và lúc khôi
    phục phải đoán cái nào mới hơn — đoán sai là mất bản mới.
    """
    assert "rubric:pending" in DRAFTS
    assert "rubricDraftKey(" in DRAFTS.split("export function rubricDraftKey")[1].split("}")[0].split("\n")[0] \
        or "export function rubricDraftKey(): string" in DRAFTS, "khoá không được nhận tham số"


def test_restoring_a_saved_versions_draft_reloads_selected():
    """Thiếu bước này thì Lưu gọi update(selected!.template_version_id) trên null."""
    restore = RUBRIC_PAGE[RUBRIC_PAGE.index("readDraft<any>(rubricDraftKey())") - 200:]
    restore = restore[: restore.index("}, [loading]);")]
    assert "rubricApi.getVersion(stored.selected_id)" in restore
    assert "setSelected(" in restore


def test_lost_access_deletes_the_local_draft():
    """Nháp nằm trong localStorage không mã hoá — không được giữ khi mất quyền."""
    assert "[403, 404].includes" in RUBRIC_PAGE
    assert RUBRIC_PAGE.count("purgeRubricDrafts()") >= 2


def test_draft_is_purged_once_saved_to_the_server():
    """Nháp trong trình duyệt không còn là bản mới nhất sau khi lưu."""
    save_block = RUBRIC_PAGE[RUBRIC_PAGE.index("const save = async"):]
    save_block = save_block[: save_block.index("const act = async")]
    assert "purgeRubricDrafts()" in save_block


def test_draft_does_not_contain_the_raw_jd():
    """localStorage không mã hoá. Nháp chỉ chứa rubric HR đang viết, không chứa JD."""
    snapshot = RUBRIC_PAGE[RUBRIC_PAGE.index("const currentDraft = () => ({"):]
    snapshot = snapshot[: snapshot.index("});")]
    assert "jd_text" not in snapshot, "nháp không được chứa JD gốc"
    assert "jdText" not in snapshot, "nháp không được chứa JD gốc"


# ---------------------------------------------------------------------------
# Trang Careers: nav phải nối vào bộ lọc có thật, không phải link chết
# ---------------------------------------------------------------------------

CAREERS = (BACKEND.parent / "frontend" / "src" / "app" / "careers" / "page.tsx").read_text()
CAREERS_API = (BACKEND / "app" / "api" / "careers.py").read_text()


def test_nav_categories_come_from_real_filter_data():
    """Nav dựng từ filters.employment_types, không phải danh sách viết cứng.

    Viết cứng "Full-time / Part-time / Internship" như mẫu thì mỗi mục bấm vào
    là danh sách rỗng, vì cột employment_type của vị trí thường bỏ trống.
    """
    nav = CAREERS[CAREERS.index('aria-label={t(\'Danh mục việc làm\')}'):]
    nav = nav[: nav.index("</Box>")]
    assert "filters.employment_types.map" in nav
    for hardcoded in ("Internship", "Part-time", "Work-study"):
        assert hardcoded not in nav, f"nhãn viết cứng {hardcoded} sẽ dẫn tới danh sách rỗng"


def test_nav_says_so_when_no_category_exists():
    """Thanh nav trống trơn khiến ứng viên tưởng trang hỏng."""
    assert "Chưa có tin nào được gắn loại việc làm." in CAREERS


def test_type_filter_exists_in_only_one_place():
    """Cùng một bộ lọc nằm hai chỗ thì bấm bên này trông như bên kia không ăn."""
    assert CAREERS.count("filters.employment_types.map") == 1


def test_search_filters_locally_without_an_api_call():
    """Số tin còn hạn đủ nhỏ; gọi API mỗi lần gõ là thừa và gây nhấp nháy."""
    # Một dòng sau khi tách logic, nên cắt theo dấu xuống dòng thay vì theo
    # "}, [jobs, titleQuery]);" — chuỗi đó không còn vì không còn thân hàm dài.
    block = CAREERS[CAREERS.index("const visibleJobs = useMemo"):].split("\n")[0]
    # Logic đã tách sang lib/careersFilter.ts để test được mà không cần render
    # React; trang chỉ gọi hàm đó. Kiểm cả hai đầu để phép tách không bị làm
    # rỗng: nếu trang tự filter lại thì hàm kia thành mã chết.
    assert "filterJobs(jobs, titleQuery)" in block
    assert "fetch(" not in block

    filt = (BACKEND.parent / "frontend" / "src" / "lib" / "careersFilter.ts").read_text()
    body = filt[filt.index("export function filterJobs"):]
    assert "jobs.filter(" in body
    assert "fetch(" not in body


def test_search_reports_no_match_instead_of_showing_nothing():
    assert "Không có vị trí nào khớp từ khóa." in CAREERS


def test_listing_empty_state_explains_intake_is_closed():
    """Trang trống phải nói lý do, không để ứng viên đoán là trang hỏng."""
    assert "INTAKE_NOT_OPEN" in CAREERS
    assert "INTAKE_NOT_OPEN" in CAREERS_API


def test_rubric_gate_is_in_the_sql_not_the_ui():
    """Ẩn tin bằng giao diện thì vẫn còn một trang có tin bấm vào không nộp được."""
    sql = CAREERS_API[CAREERS_API.index("SELECT p.position_id"):]
    sql = sql[: sql.index("LIMIT :limit")]
    assert "c.status='APPROVED'" in sql
    assert "c.jd_version_id=jd.jd_version_id" in sql


def test_stale_comment_about_the_listing_being_read_only_is_gone():
    """Câu cũ nói trang luôn là "danh sách tham khảo" đã sai sau khi chốt chính sách."""
    assert "nên trang vẫn là danh sách tham khảo" not in CAREERS_API


def test_superseded_can_never_be_the_newest_version():
    """Vì sao frontend KHÔNG cần lọc SUPERSEDED khi chọn bộ hiện tại.

    `currentCriteria = criteriaVersions[0]` (mới nhất) đã đúng, vì SUPERSEDED
    chỉ được đặt cho một bộ **cũ hơn** bộ vừa được duyệt trong cùng lệnh. Nếu
    ai thêm "ưu tiên APPROVED" vào đó thì bản nháp mới hơn mà HR cần xử lý sẽ
    bị giấu đi — đúng thứ comment trong trang cảnh báo phải tránh.
    """
    approve = CRITERIA[CRITERIA.index("new_status, reviewer_role = criteria_decision"):]
    approve = approve[: approve.index("updated = dict(")]
    supersede = approve[approve.index("UPDATE app_private.criteria_versions"):]
    supersede = supersede[: supersede.index("RETURNING")]
    # Điều kiện phải loại trừ chính bộ đang duyệt: nếu không, tự nó bị hạ.
    assert "status = 'APPROVED'" in supersede
    assert "criteria_version_id <> :cv_id" in supersede


# ---------------------------------------------------------------------------
# Áp rubric khác nhóm: giao diện đã cảnh báo, máy chủ phải chặn
# ---------------------------------------------------------------------------

RUBRIC_LIB = (BACKEND / "app" / "api" / "rubric_library.py").read_text()


def test_cross_family_apply_is_rejected_by_default():
    """Dán nhãn đỏ ở giao diện là chưa đủ: gọi thẳng API vẫn áp được."""
    apply = RUBRIC_LIB[RUBRIC_LIB.index("def apply_template"):]
    assert "allow_other_family" in apply
    assert "409" in apply


def test_cross_family_flag_defaults_to_false():
    """Mặc định phải là từ chối; cờ quên truyền không được thành cho phép."""
    assert "allow_other_family: bool = False" in RUBRIC_LIB


def test_same_family_is_never_blocked():
    """Cùng nhóm thì không được chặn — đó là đường bình thường."""
    apply = RUBRIC_LIB[RUBRIC_LIB.index("def apply_template"):]
    guard = apply[apply.index("position_family"):]
    guard = guard[: guard.index("raise HTTPException") + 200]
    assert "!= str(source['job_family_id'])" in guard


def test_position_without_family_still_works():
    """Vị trí chưa gán nhóm thì không có gì để so — không được chặn oan."""
    apply = RUBRIC_LIB[RUBRIC_LIB.index("def apply_template"):]
    guard = apply[apply.index("position_family"):]
    assert "if (position_family and" in guard


def test_frontend_only_raises_the_flag_for_a_mismatched_family():
    """Gửi cờ vô điều kiện thì chốt chặn ở máy chủ thành vô nghĩa."""
    comp = (BACKEND.parent / "frontend" / "src" / "components" / "positions" / "ApplyRubric.tsx").read_text()
    assert "chosen.job_family_id !== jobFamilyId" in comp
    assert "rubricApi.apply(positionId, selected, crossFamily)" in comp


# ---------------------------------------------------------------------------
# ADMIN xuất bản được rubric
# ---------------------------------------------------------------------------

def test_publish_permission_matches_capabilities():
    """`can_publish` và chốt chặn ở endpoint publish phải khớp tuyệt đối.

    Nếu lệch nhau: giao diện hiện nút "Xuất bản" rồi bấm vào nhận 403, hoặc
    ngược lại giấu nút trong khi API vẫn cho làm — cả hai đều là lỗi đã từng
    xảy ra ở chỗ khác trong dự án này.

    Đây là chỗ dễ tái phát nhất: hai biểu thức nằm cách nhau gần 100 dòng, và
    lần sửa trước chỉ sửa `can_create` nên `can_publish` bị bỏ quên.
    """
    caps = RUBRICS[RUBRICS.index("def capabilities"):RUBRICS.index("@router.get('/families')")]
    pub = RUBRICS[RUBRICS.index("def publish"):RUBRICS.index("@router.post('/versions/{version_id}/clone'")]
    assert "'can_publish': bool(roles.intersection({'ADMIN', 'HR_LEAD'}))" in caps
    assert "if not roles.intersection({'ADMIN', 'HR_LEAD'}):" in pub
    # Không được quay lại điều kiện chỉ HR_LEAD.
    assert "'can_publish': 'HR_LEAD' in roles" not in caps
    assert "if 'HR_LEAD' not in roles" not in pub


def test_publish_still_requires_a_lead_or_admin():
    """Nới cho ADMIN không có nghĩa là mở cho mọi vai trò."""
    pub = RUBRICS[RUBRICS.index("def publish"):RUBRICS.index("@router.post('/versions/{version_id}/clone'")]
    assert "403" in pub
    assert "HR_RECRUITER" not in pub
