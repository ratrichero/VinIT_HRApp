/**
 * One deterministic HR dataset, shared by the screenshot run and the UX metric
 * run so both describe the same screen. No live staging records are read.
 *
 * `workQueue()` mirrors `backend/app/services/workspace.py:summarize_applications`:
 * NOT_ASSESSED rows are counted as `not_assessed` and skipped before
 * `needs_verification`, which is the drift UX-R1 is about.
 */
const zlib = require('node:zlib');

/**
 * A real (if tiny) .docx built at test time: a ZIP with the WordprocessingML
 * package. Serving real bytes is the point — the preview feature unzips and
 * parses the file the reviewer actually downloads.
 */
const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();
function crc32(buffer) {
  let c = -1;
  for (let i = 0; i < buffer.length; i += 1) c = CRC_TABLE[(c ^ buffer[i]) & 0xff] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
function buildZip(files) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const file of files) {
    const name = Buffer.from(file.name, 'utf8');
    const data = Buffer.from(file.data, 'utf8');
    const deflated = zlib.deflateRawSync(data);
    const useDeflate = deflated.length < data.length;
    const payload = useDeflate ? deflated : data;
    const method = useDeflate ? 8 : 0;
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(method, 8);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(payload.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    locals.push(local, name, payload);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(method, 10);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(payload.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, name);
    offset += local.length + name.length + payload.length;
  }
  const centralSize = centrals.reduce((total, chunk) => total + chunk.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, ...centrals, end]);
}
const DOCX_PARAGRAPHS = [
  'Vũ Thị Docx',
  'Senior Backend Engineer · 6 năm kinh nghiệm',
  '',
  'Kinh nghiệm: xây dựng hệ thống thanh toán cho 2 triệu giao dịch mỗi ngày, dẫn dắt 4 kỹ sư.',
  'Học vấn: Kỹ sư Công nghệ thông tin, Đại học Bách khoa Hà Nội.',
];
// A CV table, the layout student CVs use most. Its first row is a real Word header
// row (w:tblHeader), so the reader keeps it as a header instead of guessing.
const DOCX_TABLE = [
  ['Thời gian', 'Công ty', 'Vai trò'],
  ['2022–2026', 'VinIT', 'Backend Engineer'],
];
function docxBytes() {
  const escape = text => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const body = DOCX_PARAGRAPHS.map(text => (text === ''
    ? '<w:p/>'
    : `<w:p><w:r><w:t xml:space="preserve">${escape(text)}</w:t></w:r></w:p>`)).join('');
  const table = `<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>${
    DOCX_TABLE.map((row, index) => `<w:tr>${index === 0 ? '<w:trPr><w:tblHeader/></w:trPr>' : ''}${
      row.map(cell => `<w:tc><w:p><w:r><w:t xml:space="preserve">${escape(cell)}</w:t></w:r></w:p></w:tc>`).join('')
    }</w:tr>`).join('')
  }</w:tbl>`;
  return buildZip([
    { name: '[Content_Types].xml', data: '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>' },
    { name: 'word/document.xml', data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${body}${table}</w:body></w:document>` },
  ]);
}

const POSITION = {
  position_id: 'p1',
  position_code: 'REQ-2026-014',
  title: 'Senior Backend Engineer (Python)',
  status: 'OPEN',
  department_id: 'd1',
  department_name: 'Nền tảng & Hạ tầng',
  criteria_status: 'APPROVED',
};

// The approved rubric, as `GET /criteria/position/p1/approved` returns it. The
// assessment response only carries criterion names, so U2 reads the requirement
// text from here. c1 has description + spec, c2 has guidance, c3 has neither (so
// the card must not show an empty toggle), c4 has a JD reference only.
const RUBRIC = {
  criteria_version_id: 'cv1',
  position_id: 'p1',
  jd_version_id: 'jd1',
  version_number: 1,
  status: 'APPROVED',
  origin: 'HR_CREATED',
  mandatory_weight_total: 70,
  nice_to_have_weight_total: 30,
  criteria: [
    {
      criterion_id: 'c1',
      criteria_version_id: 'cv1',
      name: 'Kinh nghiệm Python cho dịch vụ production',
      description: 'Xây dựng và vận hành dịch vụ Python chạy thật, có tải production và số liệu độ trễ.',
      category: 'MUST_HAVE',
      weight_in_group: 60,
      expected_evidence_keywords: ['FastAPI', 'asyncio'],
      requirement_spec: { kind: 'YEARS', terms: ['FastAPI'], min_years: 3, required_languages: [], required_degree_level: null },
      evidence_guidance: 'Tên hệ thống, lưu lượng, p99 và vai trò cụ thể của ứng viên.',
      jd_reference_text: 'Production Python services with measurable latency',
      display_order: 1,
    },
    {
      criterion_id: 'c2',
      criteria_version_id: 'cv1',
      name: 'Thiết kế cơ sở dữ liệu quan hệ và tối ưu truy vấn',
      description: 'Thiết kế schema quan hệ và tối ưu truy vấn có số liệu trước/sau.',
      category: 'MUST_HAVE',
      weight_in_group: 40,
      expected_evidence_keywords: ['PostgreSQL', 'index'],
      requirement_spec: null,
      evidence_guidance: 'Số liệu thời gian truy vấn trước và sau khi tối ưu, không chỉ tên công nghệ.',
      jd_reference_text: null,
      display_order: 2,
    },
    {
      criterion_id: 'c3',
      criteria_version_id: 'cv1',
      name: 'Kinh nghiệm dẫn dắt nhóm kỹ thuật nhỏ',
      description: '',
      category: 'NICE_TO_HAVE',
      weight_in_group: 100,
      expected_evidence_keywords: [],
      requirement_spec: null,
      evidence_guidance: null,
      jd_reference_text: null,
      display_order: 3,
    },
  ],
};

const CRITERIA = [
  {
    result_id: 'r-c1', hr_reviews: [], criterion_id: 'c1', criterion_name: 'Kinh nghiệm Python cho dịch vụ production', category: 'MUST_HAVE',
    outcome: 'STRONG_MATCH', score: 92, confidence: 0.91, decision_source: 'HYBRID', evidence_strength: 0.88,
    requires_verification: false, page_number: 2,
    reasoning: 'Ứng viên mô tả 4 năm xây dịch vụ FastAPI cho 1.2 triệu request/ngày và nêu rõ cách xử lý backpressure.',
    verbatim_quote: 'Thiết kế lại luồng ingest bằng FastAPI + asyncio, xử lý 1.2 triệu request/ngày với p99 dưới 120ms.',
    evidence: [{ evidence_id: 'e1', verbatim_quote: 'Thiết kế lại luồng ingest bằng FastAPI + asyncio, xử lý 1.2 triệu request/ngày với p99 dưới 120ms.', page_number: 2, verification_status: 'VERIFIED' }],
  },
  {
    result_id: 'r-c2', hr_reviews: [], criterion_id: 'c2', criterion_name: 'Thiết kế cơ sở dữ liệu quan hệ và tối ưu truy vấn', category: 'MUST_HAVE',
    outcome: 'MATCH', score: 78, confidence: 0.72, decision_source: 'AI', evidence_strength: 0.64,
    requires_verification: true, page_number: 3,
    reasoning: 'Có nhắc tới PostgreSQL và index, nhưng chưa nêu số liệu trước/sau tối ưu nên chưa xác minh được mức độ.',
    verbatim_quote: 'Tối ưu truy vấn báo cáo trên PostgreSQL, thêm composite index cho bảng events.',
    evidence: [{ evidence_id: 'e2', verbatim_quote: 'Tối ưu truy vấn báo cáo trên PostgreSQL, thêm composite index cho bảng events.', page_number: 3, verification_status: 'UNVERIFIED' }],
  },
  {
    result_id: 'r-c3', hr_reviews: [], criterion_id: 'c3', criterion_name: 'Kinh nghiệm dẫn dắt nhóm kỹ thuật nhỏ', category: 'NICE_TO_HAVE',
    outcome: 'UNCLEAR', score: null, confidence: 0.4, decision_source: 'AI', evidence_strength: 0.31,
    requires_verification: true, page_number: null,
    reasoning: 'CV chỉ nêu vai trò "technical lead" mà không nói quy mô nhóm hay phạm vi trách nhiệm.',
    verbatim_quote: 'Technical lead cho mảng thanh toán nội bộ.',
    evidence: [{ evidence_id: 'e3', verbatim_quote: 'Technical lead cho mảng thanh toán nội bộ.', page_number: 4, verification_status: 'UNVERIFIED' }],
  },
  {
    result_id: 'r-c4', hr_reviews: [], criterion_id: 'c4', criterion_name: 'Kinh nghiệm vận hành Kubernetes trên cloud', category: 'NICE_TO_HAVE',
    outcome: 'NO_MATCH', score: 0, confidence: 0.83, decision_source: 'RULE', evidence_strength: 0.9,
    requires_verification: false, page_number: null,
    reasoning: 'Không tìm thấy từ khoá Kubernetes, EKS hay GKE trong CV.',
    verbatim_quote: null, evidence: [],
  },
];

const NAMES = [
  'Nguyễn Minh Anh', 'Trần Quốc Bảo', 'Lê Thu Hà', 'Phạm Đình Khang', 'Hoàng Mai Linh', 'Đỗ Văn Nam',
  'Vũ Thị Ngọc', 'Bùi Anh Tuấn', 'Ngô Thanh Tùng', 'Dương Hồng Yến', 'Lý Gia Hân', 'Phan Trọng Nghĩa',
];

const STATUSES = [
  'NEEDS_HR_VERIFICATION', 'MEETS_MANDATORY', 'NEEDS_HR_VERIFICATION', 'POSSIBLE_MISMATCH',
  'MEETS_MANDATORY', 'NEEDS_HR_VERIFICATION', 'MEETS_MANDATORY', 'NOT_ASSESSED',
  'NEEDS_HR_VERIFICATION', 'POSSIBLE_MISMATCH', 'MEETS_MANDATORY', 'NOT_ASSESSED',
];

const COVERAGES = [0.55, 0.92, 0.61, 0.78, 0.88, 0.49, 0.95, 0, 0.66, 0.74, 0.9, 0];
const SCORES = [72, 88, 69, 61, 83, 58, 91, null, 64, 67, 86, null];

const ranking = NAMES.map((name, index) => {
  const status = STATUSES[index];
  const coverage = COVERAGES[index];
  return {
    application_id: `app-${index}`,
    position_id: 'p1',
    candidate_name: name,
    rank_number: status === 'NOT_ASSESSED' || coverage < 0.7 ? null : index + 1,
    matching_status: status,
    matching_score: SCORES[index],
    evidence_coverage: coverage,
    ltr_score: null,
    needs_verification: status === 'NEEDS_HR_VERIFICATION' || (coverage > 0 && coverage < 0.7),
    has_mismatch: status === 'POSSIBLE_MISMATCH',
    criterion_results: CRITERIA.map(c => ({
      criterion_id: c.criterion_id, criterion_name: c.criterion_name, category: c.category,
      outcome: c.outcome, score: c.score, effective_weight: 30, requires_verification: c.requires_verification,
    })),
    file_processing_status: index === 5 ? 'NEEDS_HR_REVIEW' : index === 7 ? 'PROCESSING' : 'COMPLETED',
    file_error: index === 5 ? 'PDF có 3 trang scan không trích xuất được text.' : null,
    has_duplicate_warning: index === 3 || index === 9,
    is_shortlisted: index === 1 || index === 6,
    application_status: index === 1 || index === 6 ? 'SHORTLIST' : index === 11 ? 'NEW' : 'IN_REVIEW',
    created_at: `2026-10-${String(12 + index).padStart(2, '0')}T08:30:00Z`,
  };
});

// One duplicate pair so the ranking list can show who a flagged row duplicates.
// app-3 and app-9 both carry has_duplicate_warning above.
const DUPLICATE_SIGNALS = [
  {
    signal_id: 'sig-1',
    signal_type: 'SAME_EMAIL',
    confidence: 0.92,
    detector_version: 'v1',
    review_status: 'UNREVIEWED',
    created_at: '2026-11-01T08:00:00Z',
    application_id_1: 'app-3',
    candidate_name_1: 'Phạm Đình Khang',
    application_id_2: 'app-9',
    candidate_name_2: 'Dương Hồng Yến',
  },
];

// Cặp hồ sơ trong DUPLICATE_SIGNALS, mỗi bên một định danh và một bộ kết quả
// tiêu chí khác nhau — màn so sánh chỉ có nghĩa khi hai bên thật sự khác nhau.
// c4 giống nhau (đều chưa đáp ứng) để có cả dòng trùng kết luận.
const COMPARE_APPLICATIONS = {
  'app-3': {
    name: 'Phạm Đình Khang',
    email: 'khang.pham@example.com',
    phone: '0912 345 671',
    score: 61,
    coverage: 0.58,
    results: {
      c1: { outcome: 'MATCH', score: 70, page: 2 },
      c2: { outcome: 'UNCLEAR', score: null, page: 3 },
      c3: { outcome: 'MATCH', score: 80, page: 4 },
      c4: { outcome: 'NO_MATCH', score: 0, page: null },
    },
  },
  'app-9': {
    name: 'Dương Hồng Yến',
    email: 'yen.duong@example.com',
    phone: '0987 654 321',
    score: 86,
    coverage: 0.9,
    results: {
      c1: { outcome: 'STRONG_MATCH', score: 92, page: 3 },
      c2: { outcome: 'MATCH', score: 78, page: 2 },
      c3: { outcome: 'UNCLEAR', score: null, page: 5 },
      c4: { outcome: 'NO_MATCH', score: 0, page: null },
    },
  },
};

const applications = ranking.map(item => ({
  application_id: item.application_id,
  position_id: 'p1',
  candidate_name: item.candidate_name,
  application_status: item.application_status,
  file_processing_status: item.file_processing_status,
  file_error: item.file_error,
  has_duplicate_warning: item.has_duplicate_warning,
  created_at: item.created_at,
  identity: { display_name: item.candidate_name },
}));

const inScreening = status => ['NEW', 'IN_REVIEW', 'SHORTLIST'].includes(status || '');
const visible = ranking.filter(item => inScreening(item.application_status));

const workQueueSummary = {
  positions_needing_attention: 2,
  files_needing_review: visible.filter(item => item.file_processing_status === 'NEEDS_HR_REVIEW').length,
  applications_needing_verification: visible.filter(item => item.matching_status !== 'NOT_ASSESSED'
    && (item.matching_status === 'NEEDS_HR_VERIFICATION' || item.evidence_coverage < 0.7)).length,
  // Mirrors the backend's verification_complete bucket: rows a reviewer finished
  // checking. Kept separate so the dashboard can show finished work instead of
  // only shrinking the pending number.
  applications_verification_complete: 3,
  duplicate_alerts: visible.filter(item => item.has_duplicate_warning).length,
  criteria_pending_action: 1,
  shares_without_feedback: 2,
};

const workQueue = {
  generated_at: '2026-11-19T03:00:00Z',
  summary: workQueueSummary,
  items: [
    { item_id: 'FILE_REVIEW:p1', type: 'FILE_REVIEW', priority: 'HIGH', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: workQueueSummary.files_needing_review, target: { pathname: '/positions/p1/applicants', search: 'queue=FILE_REVIEW' } },
    { item_id: 'NEEDS_VERIFICATION:p1', type: 'NEEDS_VERIFICATION', priority: 'HIGH', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: workQueueSummary.applications_needing_verification, target: { pathname: '/positions/p1/applicants', search: 'queue=NEEDS_VERIFICATION' } },
    { item_id: 'CRITERIA_PENDING_HM:p3', type: 'CRITERIA_PENDING_HM', priority: 'HIGH', position_id: 'p3', position_code: 'REQ-2026-021', position_title: 'Data Engineer', position_status: 'OPEN', count: 1, target: { pathname: '/positions/p3', search: 'tab=criteria' } },
    { item_id: 'DUPLICATE_PENDING:p1', type: 'DUPLICATE_PENDING', priority: 'MEDIUM', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: workQueueSummary.duplicate_alerts, target: { pathname: '/positions/p1/applicants', search: 'queue=DUPLICATE' } },
    { item_id: 'POSSIBLE_MISMATCH:p1', type: 'POSSIBLE_MISMATCH', priority: 'MEDIUM', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: visible.filter(item => item.matching_status === 'POSSIBLE_MISMATCH').length, target: { pathname: '/positions/p1/applicants', search: 'queue=POSSIBLE_MISMATCH' } },
    { item_id: 'NOT_ASSESSED:p1', type: 'NOT_ASSESSED', priority: 'MEDIUM', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: visible.filter(item => item.matching_status === 'NOT_ASSESSED').length, target: { pathname: '/positions/p1/applicants', search: 'queue=NOT_ASSESSED' } },
    { item_id: 'SHARE_WITHOUT_FEEDBACK:p1', type: 'SHARE_WITHOUT_FEEDBACK', priority: 'LOW', position_id: 'p1', position_code: POSITION.position_code, position_title: POSITION.title, position_status: 'OPEN', count: 2, target: { pathname: '/shortlist', search: '' } },
  ],
};

const dashboardSummary = {
  open_positions: 4,
  total_applications: 38,
  applications_by_status: {
    NEW: 6, IN_REVIEW: 14, SHORTLIST: 5, REJECTED_SCREENING: 7,
    INTERVIEW: 3, REJECTED_INTERVIEW: 2, OFFERED: 1, ACCEPTED: 0,
  },
  applications_processing: 2,
  // Same source as the work-queue summary above, so the card and the queue
  // subtitle cannot disagree in the screenshot.
  files_needing_hr_review: workQueueSummary.files_needing_review,
  files_needing_review: workQueueSummary.files_needing_review,
  files_needing_review_rate: 0.03,
  duplicate_alerts: workQueueSummary.duplicate_alerts,
  assessments_completed: 31,
  average_coverage: 0.74,
  coverage_sample_size: 31,
  coverage_under_threshold: 9,
};

const detail = {
  application_id: 'app-2',
  position_id: 'p1',
  source_code: 'CAREERS',
  application_status: 'IN_REVIEW',
  created_at: '2026-10-14T08:30:00Z',
  candidate_name: 'Lê Thu Hà',
  can_view_cv: true,
  can_update_status: true,
  // A recruiter on the position holds both gates: status and HR notes. The
  // status-only shape (update without notes) belongs to app-admin below; using
  // it here would hide a real 403 behind a mock that answers 201 anyway.
  can_manage_hr_notes: true,
  can_view_assessment_evidence: true,
  capabilities: {
    view_cv: true, view_evidence: true, update_status: true, review_evidence: true,
    manage_hr_notes: true, edit_profile: true, view_status_history: true, reprocess_cv: true,
  },
  file_processing_status: 'COMPLETED',
  has_duplicate_warning: false,
  documents: [{ document_id: 'doc1', document_type: 'CV', original_filename: 'Le_Thu_Ha_CV_2026.pdf', mime_type: 'application/pdf', page_count: 4 }],
  identity: { display_name: 'Lê Thu Hà', email: 'le.thu.ha@example.com', phone: '09xx xxx 214' },
  latest_assessment: {
    assessment_id: 'a1',
    position_id: 'p1',
    application_id: 'app-2',
    matching_status: 'NEEDS_HR_VERIFICATION',
    matching_score: 69,
    evidence_coverage: 0.61,
    summary: 'Đáp ứng phần lớn yêu cầu bắt buộc; hai tiêu chí cần HR xác minh bằng chứng trước khi xếp hạng.',
    criterion_results: CRITERIA,
  },
};

const me = {
  user_id: 'u-hr', display_name: 'Nguyễn Thu Hằng', must_change_password: false,
  system_roles: ['HR_RECRUITER'], position_roles: ['HR_RECRUITER'],
  position_assignments: [
    { position_id: 'p1', position_role: 'HR_RECRUITER' },
    { position_id: 'p3', position_role: 'HR_RECRUITER' },
    { position_id: 'p4', position_role: 'HIRING_MANAGER' },
  ],
};

const statusEvents = [
  { event_id: 'ev1', previous_status: 'NEW', new_status: 'IN_REVIEW', reason: null, note: 'Bắt đầu rà soát bằng chứng.', changed_at: '2026-10-15T02:10:00Z', changed_by_name: 'Nguyễn Thu Hằng' },
];

const profile = {
  profile_version_id: 'pv1', version_number: 1,
  identity: { display_name: 'Lê Thu Hà', email: 'le.thu.ha@example.com', phone: '09xx xxx 214' },
  facts: [],
};

/**
 * Install the mock API on a Playwright context. `overrides` maps a path to a
 * handler so a test can change one answer (e.g. simulate a status change).
 */
function installMockApi(context, overrides = {}) {
  const unexpected = [];
  // A review recorded during the test must come back on the reload, otherwise the
  // test could pass on an optimistic UI that never actually persisted anything.
  const reviews = {};
  const route = async r => {
    const url = new URL(r.request().url());
    const p = url.pathname;
    if (overrides[p]) return overrides[p](r, url);
    const json = (body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (p === '/v1/auth/me') return json(me);
    if (p === '/v1/dashboard/summary') return json(dashboardSummary);
    // The shortlist index calls this on mount. It was never mocked, so the page
    // got a 500 body and crashed with "Application error" — invisible to every
    // test that only walked the shortlist detail route.
    if (p === '/v1/shortlist/shared-with-me') return json([]);
    if (p === '/v1/dashboard/work-queue') return json(workQueue);
    if (p === '/v1/scorecards/reminders') return json([]);
    // Chuông thông báo trong AppLayout hỏi hộp thư ngay khi mount (và mỗi 60s).
    // Hộp thư rỗng: các e2e này không kiểm thông báo, và số 0 không đổi bố cục.
    if (p === '/v1/notifications' && r.request().method() === 'GET') return json({ items: [], unread_count: 0 });
    if (p === '/v1/positions' && r.request().method() === 'GET') return json([POSITION]);
    if (p === '/v1/positions/p1') return json(POSITION);
    if (p === '/v1/assessments/ranking/latest/p1') return json(ranking);
    if (p === '/v1/applications') return json(applications);
    // Khối "Lịch phỏng vấn" trong hồ sơ gọi danh sách buổi phỏng vấn ngay khi
    // mount. Thiếu route này thì mọi e2e đi qua trang hồ sơ đều thấy thêm một
    // request lạ (`GET /v1/interviews`) và đỏ ở assert "không gọi endpoint lạ"
    // — lỗi của mock, không phải của trang. Trả rỗng: các e2e này không kiểm
    // lịch phỏng vấn, và danh sách rỗng không đổi bố cục trang.
    if (p === '/v1/interviews' && r.request().method() === 'GET') return json([]);
    if (p === '/v1/operations/position/p1/active') return json(null);
    if (p === '/v1/positions/p1/duplicate-signals') return json(DUPLICATE_SIGNALS);
    if (p === '/v1/criteria/position/p1/approved') return json(RUBRIC);
    if (p === '/v1/shortlist/potential-recipients/p1') return json([]);
    if (p === '/v1/applications/app-2') {
      return json({
        ...detail,
        latest_assessment: {
          ...detail.latest_assessment,
          // Mỗi hồ sơ một result_id riêng, như bảng thật. Bản cũ trả id trần
          // (`r-c2`) nên nhiều hồ sơ dùng chung một id: xác nhận ở hồ sơ này sẽ
          // hiện thành "đã kiểm" ở hồ sơ khác, và không thể kiểm được "mỗi dòng
          // một POST".
          criterion_results: (detail.latest_assessment?.criterion_results || CRITERIA).map(c => {
            const resultId = `app-2:${c.result_id}`;
            return { ...c, result_id: resultId, hr_reviews: reviews[resultId] || [] };
          }),
        },
      });
    }
    const reviewMatch = p.match(/^\/v1\/assessments\/results\/([^/]+)\/review$/);
    if (reviewMatch && r.request().method() === 'POST') {
      const body = JSON.parse(r.request().postData() || '{}');
      const resultId = reviewMatch[1];
      if (body.decision === 'REJECTED' && !(body.comment || '').trim()) {
        return json({ detail: 'Cần nêu lý do khi đánh dấu bằng chứng không đúng' }, 400);
      }
      const review = {
        review_id: `rev-${Object.keys(reviews).length + 1}`,
        decision: body.decision,
        comment: body.comment || null,
        reviewer_user_id: 'u-hr',
        reviewer_name: 'Nguyễn Thu Hằng',
        created_at: '2026-11-19T09:15:00Z',
      };
      // Append-only, like the table: a second look is a new row.
      reviews[resultId] = [review, ...(reviews[resultId] || [])];
      return r.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(review) });
    }
    if (p === '/v1/applications/app-2/status-events') return json(statusEvents);
    if (p === '/v1/applications/app-2/profile') return json(profile);
    if (p === '/v1/applications/app-2/cv-file') {
      return r.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4\n' });
    }
    // A reviewer who may verify evidence but may NOT change the application
    // status: the finish action must still work, with no status picker.
    if (p === '/v1/applications/app-verifier') {
      return json({
        ...detail,
        application_id: 'app-verifier',
        candidate_name: 'Đỗ Minh Xác',
        identity: { ...detail.identity, display_name: 'Đỗ Minh Xác' },
        // Verifies evidence only: the review endpoint's gate is this flag, while
        // the finish action must not require the status permission.
        can_update_status: false,
        can_manage_hr_notes: true,
        capabilities: {
          view_cv: true, view_evidence: true, update_status: false, review_evidence: true,
          manage_hr_notes: true, edit_profile: false, view_status_history: false, reprocess_cv: false,
        },
        latest_assessment: { ...detail.latest_assessment, application_id: 'app-verifier' },
      });
    }
    // A status-only reviewer (mirrors a global ADMIN): may change status, may
    // not record criterion reviews or HR notes. The review endpoint would answer
    // 403, so the screen must not offer the verification controls.
    if (p === '/v1/applications/app-admin') {
      return json({
        ...detail,
        application_id: 'app-admin',
        candidate_name: 'Lý Quản Trị',
        identity: { ...detail.identity, display_name: 'Lý Quản Trị' },
        can_update_status: true,
        can_manage_hr_notes: false,
        capabilities: {
          view_cv: true, view_evidence: true, update_status: true, review_evidence: false,
          manage_hr_notes: false, edit_profile: true, view_status_history: true, reprocess_cv: true,
        },
        latest_assessment: { ...detail.latest_assessment, application_id: 'app-admin' },
      });
    }
    // Hai hồ sơ bị gắn cờ trùng (sig-1): mỗi bên một định danh và một bộ kết quả
    // tiêu chí khác nhau, để màn so sánh có việc thật mà làm. Cùng c4 (đều chưa
    // đáp ứng) để có cả dòng giống nhau lẫn dòng khác nhau.
    const compareId = p.match(/^\/v1\/applications\/(app-\d+)$/)?.[1];
    if (compareId && COMPARE_APPLICATIONS[compareId] && r.request().method() === 'GET') {
      const spec = COMPARE_APPLICATIONS[compareId];
      const row = ranking.find(item => item.application_id === compareId);
      return json({
        ...detail,
        application_id: compareId,
        candidate_name: spec.name,
        application_status: row?.application_status || 'IN_REVIEW',
        has_duplicate_warning: true,
        identity: { display_name: spec.name, email: spec.email, phone: spec.phone },
        latest_assessment: {
          ...detail.latest_assessment,
          application_id: compareId,
          matching_score: spec.score,
          evidence_coverage: spec.coverage,
          criterion_results: CRITERIA.map(item => {
            const override = spec.results[item.criterion_id];
            const page = override.page;
            // Như trên: kết quả thuộc về từng hồ sơ, nên id phải mang mã hồ sơ.
            const resultId = `${compareId}:${item.result_id}`;
            return {
              ...item,
              result_id: resultId,
              outcome: override.outcome,
              score: override.score,
              page_number: page,
              evidence: page
                ? [{ evidence_id: `e-${compareId}-${item.criterion_id}`, verbatim_quote: item.verbatim_quote || item.reasoning, page_number: page, verification_status: 'UNVERIFIED' }]
                : [],
              hr_reviews: reviews[resultId] || [],
            };
          }),
        },
      });
    }
    // Hồ sơ trượt tiêu chí bắt buộc: c1 là MUST_HAVE nhưng kết luận NO_MATCH.
    // Đây là đường dẫn tới nhánh "loại ở vòng sàng lọc" khi hoàn tất — trước đây
    // chỉ có unit test cho suggestFinishStatus, chưa có giao diện nào chạy qua.
    if (p === '/v1/applications/app-must-fail' && r.request().method() === 'GET') {
      const failedResultId = 'app-must-fail:r-c1';
      return json({
        ...detail,
        application_id: 'app-must-fail',
        candidate_name: 'Trượt Bắt Buộc',
        identity: { display_name: 'Trượt Bắt Buộc', email: 'truot.batbuoc@example.com', phone: '09xx xxx 999' },
        application_status: 'IN_REVIEW',
        has_duplicate_warning: false,
        latest_assessment: {
          ...detail.latest_assessment,
          application_id: 'app-must-fail',
          matching_status: 'POSSIBLE_MISMATCH',
          matching_score: 41,
          evidence_coverage: 0.52,
          summary: 'Trượt tiêu chí bắt buộc về kinh nghiệm Python cho dịch vụ production.',
          criterion_results: [
            {
              ...CRITERIA[0],
              result_id: failedResultId,
              outcome: 'NO_MATCH',
              score: 0,
              confidence: 0.79,
              decision_source: 'AI',
              evidence_strength: 0.55,
              // Vẫn chờ HR xác minh: một tiêu chí bắt buộc bị kết luận trượt thì
              // càng phải để HR đối chiếu trước khi loại hồ sơ.
              requires_verification: true,
              page_number: null,
              reasoning: 'Không có dòng nào trong CV mô tả dịch vụ Python chạy production, chỉ có script xử lý dữ liệu một lần.',
              verbatim_quote: null,
              evidence: [],
              hr_reviews: reviews[failedResultId] || [],
            },
            { ...CRITERIA[1], result_id: 'app-must-fail:r-c2', requires_verification: false, hr_reviews: [] },
          ],
        },
      });
    }
    if (p === '/v1/applications/app-must-fail/status' && r.request().method() === 'PATCH') {
      const body = JSON.parse(r.request().postData() || '{}');
      return json({ ...detail, application_id: 'app-must-fail', application_status: body.new_status });
    }
    // Any other application row from the ranking can be opened too: finishing a
    // profile advances to the next one, and that page must load in the mock.
    const applicationMatch = p.match(/^\/v1\/applications\/(app-\d+)$/);
    if (applicationMatch && r.request().method() === 'GET') {
      const id = applicationMatch[1];
      const row = ranking.find(item => item.application_id === id);
      return json({
        ...detail,
        application_id: id,
        candidate_name: row?.candidate_name || detail.candidate_name,
        identity: { ...detail.identity, display_name: row?.candidate_name || detail.identity.display_name },
        application_status: row?.application_status || detail.application_status,
        latest_assessment: {
          ...detail.latest_assessment,
          application_id: id,
          // Mỗi hồ sơ một result_id riêng, đúng như bảng thật: xác minh ở hồ sơ
          // này không được biến hồ sơ khác thành "đã kiểm".
          criterion_results: CRITERIA.map(c => {
            const resultId = `${id}:${c.result_id}`;
            return { ...c, result_id: resultId, hr_reviews: reviews[resultId] || [] };
          }),
        },
      });
    }
    const statusMatch = p.match(/^\/v1\/applications\/(app-\d+)\/status$/);
    if (statusMatch && r.request().method() === 'PATCH') {
      const body = JSON.parse(r.request().postData() || '{}');
      return json({ ...detail, application_id: statusMatch[1], application_status: body.new_status });
    }
    // A candidate whose CV is a .docx: the panel must show readable text without
    // downloading, and must still fetch nothing until HR asks.
    if (p === '/v1/applications/app-docx') {
      return json({
        ...detail,
        application_id: 'app-docx',
        candidate_name: 'Vũ Thị Docx',
        identity: { ...detail.identity, display_name: 'Vũ Thị Docx' },
        documents: [{ document_id: 'doc-docx', document_type: 'CV', original_filename: 'Vu_Thi_Docx_CV.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', page_count: 1 }],
        latest_assessment: { ...detail.latest_assessment, application_id: 'app-docx' },
      });
    }
    if (p === '/v1/applications/app-docx/cv-file') {
      return r.fulfill({ status: 200, contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', body: docxBytes() });
    }
    if (/^\/v1\/applications\/(app-[a-z0-9-]+)\/private-notes$/.test(p)) return json([]);
    if (/^\/v1\/applications\/(app-[a-z0-9-]+)\/(status-events|profile|cv-file)$/.test(p)) {
      if (p.endsWith('/status-events')) return json(statusEvents);
      if (p.endsWith('/profile')) return json(profile);
      return r.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4\n' });
    }
    unexpected.push(`${r.request().method()} ${p}${url.search}`);
    return json({});
  };
  return context.route('**/v1/**', route).then(() => unexpected);
}

module.exports = {
  POSITION, CRITERIA, RUBRIC, NAMES, ranking, applications, visible,
  workQueue, workQueueSummary, dashboardSummary, detail, me, profile,
  DOCX_PARAGRAPHS, DOCX_TABLE, docxBytes, installMockApi,
};
