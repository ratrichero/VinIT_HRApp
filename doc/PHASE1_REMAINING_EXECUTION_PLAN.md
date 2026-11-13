# Kế hoạch hoàn tất các việc còn mở — Phase 1 và các hạng mục liên quan

> Đây là bản tổng hợp/đề xuất, **không tự phê duyệt triển khai, nghiệm thu hay đóng gate**. Nguồn: trạng thái Git và code trong workspace, `doc/PENDING_DEPLOYMENT.md`, `doc/E2E_STAGING_EXECUTION_CHECKLIST.md`, `audit/PHASE1_REVIEW_2026-11-07.md`, `doc/HRA_PRD.md` và các plan Phase 2/UX/Langfuse. Các kết quả môi trường dưới đây là bằng chứng đã được ghi nhận trong phiên trước, không phải kiểm tra mới trong lần rà soát này.
>
> **Tiến triển sau ảnh chụp:** batch A đã bổ sung fence PROCESSING bền vững, recovery thủ công có xác nhận và migration `00014` trong repo; CI xanh tại commit `cf9807d`; chi tiết và giới hạn tại `RETENTION_RECOVERY_RUNBOOK.md`. Người dùng đã xác nhận A1–A6 và cho biết HR/Privacy/Legal, DevOps đồng ý các hướng liên quan; phần B tạm treo để quay lại khi cần, phần C tiếp tục chờ. Xem [`PHASE1_PRODUCTION_DEFERRED_REPORT.md`](PHASE1_PRODUCTION_DEFERRED_REPORT.md). Các trạng thái/test/diff trong mục 2.1 và thứ tự ở mục 3 là snapshot/plan lịch sử trước batch này; không coi chúng mô tả worktree hiện tại hay các gate đã đóng.
>
> **Quy tắc thời gian:** ngày hệ thống phiên hiện tại là 05/11/2026, trong khi một số commit, CI và biên bản trong repository ghi ngày 07–11/11/2026. Giữ nguyên các bằng chứng theo đúng nhãn được ghi; cần người vận hành đối chiếu đồng hồ/mốc thời gian và xác nhận lại trước khi ký nghiệm thu hoặc dùng làm mốc phát hành. Không suy diễn kết quả chỉ dựa vào thứ tự ngày.

## 1. Kết luận nhanh và nguyên tắc

- **Phase 1 chưa đóng; không coi là sẵn sàng dùng dữ liệu thật/production scale.** DEP-01 đóng có phạm vi, DEP-02 còn một phần; các gate khác vẫn có chủ trì và điều kiện riêng.
- **E2E tiếp tục tạm treo theo quyết định của người dùng.** Các bước dưới đây liên quan E2E là kế hoạch chờ mở lại, không phải lệnh chạy, kể cả UX usability hay Langfuse staging.
- Có thể chuẩn bị/review/test tự động cục bộ hoặc trên CI bằng PostgreSQL dùng một lần và dữ liệu tổng hợp; không chạy integration suite trên Supabase kết nối, không ghi dữ liệu VPS, không dùng CV thật và không bật chức năng AI mới.
- Luồng duyệt trực tiếp criteria đã được người dùng xác nhận; **không triển khai lại**. Dual approval vẫn cần kiểm chứng ở phạm vi tương ứng; cần phân biệt với ngoại lệ direct approval đã được phép.
- Giữ tiêu chí Python tối thiểu 4 năm: fixture `partial_backend` ghi 2 năm là `UNCLEAR` để HR xác minh, không tự chuyển sang `MATCH`/`NO_MATCH`; giữ manifest và known variance đã chấp nhận. Không tự thay đổi policy scoring/rubric.

## 2. Ảnh chụp trạng thái thực tế

### 2.1 Code đang dở ở workspace

| Gói | Trạng thái và bằng chứng | Việc còn trước khi coi là sẵn sàng phát hành |
|---|---|---|
| Ba ưu tiên retention/shortlist/duplicate | Có thay đổi **chưa commit, chưa push, chưa deploy** trên branch `arena/ea6e2570-vinit-hrapp`, HEAD `4f120b6`. Confirm/execute kiểm tra `CLOSED` + snapshot `closed_at`; khóa position/case/application/share qua storage và purge; chặn share note/feedback chung; API/UI chỉ đọc cặp duplicate cùng position với RBAC. | Review độc lập, hoàn thiện xử lý sự cố storage/DB và các test còn thiếu; chạy PostgreSQL integration/CI; chỉ sau đó mới bàn release. Không coi ba mục là đã nghiệm thu. |
| Kiểm thử cục bộ lượt trước | Backend **162 passed, 76 skipped**, trong đó PostgreSQL integration bỏ qua vì không có DB dùng một lần; frontend type-check, lint, unit/i18n và build đạt. | Test PostgreSQL thật (đặc biệt tranh chấp khóa, RBAC và shared feedback) chưa có kết quả cho diff này. Các CI xanh đã ghi cho commit cũ **không** áp dụng cho diff chưa commit. |
| Điểm dừng an toàn của purge | Khóa xử lý cạnh tranh thông thường, nhưng DB và storage không atomic: lỗi một phần, process crash hoặc mất DB connection có thể để file mất trong khi DB rollback và khóa được giải phóng. | Không chạy retention thật với bản mới cho tới khi có thiết kế/đánh giá recovery được duyệt và kết quả test; không khẳng định đã giải quyết crash-atomic. |

Ghi chú feedback: guard chỉ chặn văn bản chung hiện có trên share còn liên kết tới hồ sơ. Các share đã purge trước đó có thể đã mất liên kết; phản hồi riêng của người khác hoặc phản hồi mới sau purge cũng có thể nhắc tên ứng viên. Cần quyết định Privacy/HR và điều tra an toàn, không tùy tiện xóa cả feedback chung của shortlist nhiều ứng viên.

### 2.2 DEP Phase 1 — trạng thái theo bằng chứng đã ghi

| ID | Trạng thái | Việc còn / điều kiện đóng |
|---|---|---|
| DEP-01 | `CLOSED_SCOPED` theo quyết định điều phối được ghi; E2E-01, 05–09 đã có PASS; E2E-09 PASS bổ sung sau quyết định đóng scoped | E2E-02–04 chưa có PASS; HR Lead/HM ký bổ sung theo phạm vi đã quyết định. Không diễn giải scoped PASS thành toàn bộ Phase 1 PASS. |
| DEP-02 | `PARTIAL` | E2E-10/11/12 PASS theo log; E2E-13 đã purge một hồ sơ nhưng shortlist, embedding, private note chưa có trước purge, nên thiếu chứng cứ cho những loại đó. Cần quyết định phạm vi và khi được mở lại, fixture tổng hợp có các dữ liệu đó, đối chiếu storage/DB/audit và API verify sau xóa. |
| DEP-03 | `BLOCKED` | DevOps xác nhận môi trường/topology thực tế, commit backend/frontend/worker và migration, drain/mixed-version, rollback và cửa sổ deploy; snapshot mapping cũ không thay thế xác nhận hiện tại. |
| DEP-04 | `BLOCKED_MANUAL_OPS` | Kiểm kê mọi consumer, xác nhận đã dùng key/JWKS mới và khởi động đồng nhất; chủ project mới tự disable/revoke legacy và kiểm tra login sau đó. Không lưu key trong bằng chứng. Lần kiểm kê đã ghi legacy còn bật; chưa xác minh lại lần này. |
| DEP-05 | `BLOCKED` cho dữ liệu thật | IT Security/Legal/HR kiểm kê hồi cứu gateway/provider, thời gian, loại payload, lưu trữ/training/xóa và phê duyệt egress; redaction chỉ best effort. Legal/Privacy cũng xác nhận phạm vi retention 12 tháng, kể cả hồ sơ đã tuyển. |
| DEP-06 | `WAITING` | DEP-05 theo phạm vi, BGE endpoint/token/quota và HR golden set; đánh giá Recall@5, sai lệch, unresolved, latency; hash provider chỉ smoke plumbing. |
| DEP-07 | `WAITING` | HR-labelled dataset, holdout/gates, artifact hash + approval, so sánh SHADOW; chỉ xét ACTIVE sau bằng chứng. F-01 đã sửa trong code, không vì thế mà đóng gate. |
| DEP-08 | `WAITING` | DevOps/IT xác nhận branch protection, monitor/alert, topology worker, backup/restore và DR drill. GitHub API từng trả 403 khi kiểm tra protection, không chứng minh bật hay tắt. |

Theo checklist: E2E-14 OCR, E2E-15 BGE và E2E-16 recovery có điều kiện; chỉ `N/A` theo phạm vi được khóa trước và không suy ra tính năng đạt. Cần rà soát log/PII theo checklist trước bất kỳ ký duyệt đầy đủ nào.

### 2.3 Khoảng thiếu nghiệp vụ/kiểm thử Phase 1

| Phạm vi | Đã có / chưa có | Công việc còn lại |
|---|---|---|
| F1.01–04 | Tạo vị trí/JD, criteria, upload và profile có code; E2E-02–04 chưa PASS. | Khi E2E được mở lại: Admin/RBAC; dual approval và direct approval là hai luồng khác nhau; upload/profile/versioning và batch; kiểm thử UI đổi HM sau tạo ở môi trường được duyệt. OCR scan thực tế chưa được nghiệm thu. |
| F1.05–06 | Rules v1.4, score một phần/coverage và E2E-05–07 đã được ghi PASS trong phạm vi synthetic; DM-01/DM-02 đã đóng theo bằng chứng trước. | HR/HM chốt policy và đánh giá chất lượng trên dữ liệu được phép, kiểm tra quote, false MATCH/NO_MATCH và repeatability. Smoke synthetic không phải gold set. |
| F1.07 | Detector dùng exact email/phone trong cùng vị trí; thay identity dismiss pending cũ và phát hiện lại ở ranking sau. E2E-08 chỉ chứng minh một `EMAIL_MATCH`; API/UI đọc tín hiệu đã có ở commit `cf9807d`. | Người dùng chọn A4 phương án 1: chấp nhận giới hạn email/SĐT cho phạm vi Phase 1, không yêu cầu detector trùng nội dung file; không thêm cross-position/auto-merge. Đây không tự xác nhận toàn bộ nghiệm thu detector. |
| F1.08–10 | Trạng thái do HR quyết định; shortlist/feedback/revoke E2E-09 đã ghi PASS; audit/retention như DEP-02. | Đóng các lỗ hổng retention ở mục 3; xác nhận audit chính sách/ma trận quyền, không suy toàn bộ retention PASS từ E2E-09. |
| F1.11–12 | Privacy egress còn chặn dữ liệu thật; giao diện VI/EN có test. | DEP-05; review thuật ngữ/trải nghiệm VI/EN **tạm treo — chờ report** (B7 trong `PHASE1_PRODUCTION_DEFERRED_REPORT.md`), đặc biệt điểm một phần và UNCLEAR. |
| Pilot quality | `doc/HRA_NextPhase.md` gọi pilot evaluation là **F1.13**, trong khi closure review dùng F1.13 cho dashboard/worker. PRD ghi mục tiêu khoảng 300 cặp, tối thiểu đề xuất 200, HR/HM xác nhận và phân xử. | Mapping theo dõi đã thống nhất bên dưới; không bỏ sót pilot. `evaluate_matching.py` hiện chủ yếu đo repeatability, không tự chứng minh toàn bộ chất lượng extraction/matching/ranking. Thiết kế evaluation có mẫu/nhãn, nhóm IT, định nghĩa denominator, tránh leakage, phân xử, báo cáo từng nhóm; kiểm tra có đủ coverage công cụ trước khi chọn xây thêm. |
| Dashboard/worker | Có code, test và at-least-once; topology/monitoring/recovery môi trường đích chưa được chốt. | Theo DEP-03/08 và E2E-16 nếu đưa vào phạm vi. Không tuyên bố exactly-once. |

### Đối chiếu nhãn F1.13 — theo quyết định người dùng

| Nguồn | Mã / nội dung | Tình trạng |
|---|---|---|
| `HRA_NextPhase.md` | **F1.09**: shortlist + dashboard nghiệp vụ cơ bản; **F1.13**: đánh giá pilot trên tập nhãn chuẩn | Benchmark, gold và phê duyệt vận hành tạm treo; chưa có kết quả đánh giá chất lượng được nghiệm thu. |
| `audit/PHASE1_REVIEW_2026-11-07.md` và `audit/PHASE1_GAP_ANALYSIS.md` | **F1.13**: dashboard/worker trong bảng audit lịch sử | Tên mã bị dùng khác so với `HRA_NextPhase.md`; trạng thái dashboard/worker có bằng chứng code/test riêng nhưng chưa đóng gate vận hành. |

Người dùng đồng ý phương án sau cho bảng theo dõi mới: giữ F1.09 cho shortlist/dashboard nghiệp vụ, F1.13 cho pilot evaluation theo `HRA_NextPhase.md`, và theo dõi worker/recovery như hạng mục kỹ thuật liên kết F1.09 cùng DEP-03/DEP-08, E2E-16 nếu thuộc phạm vi. Dashboard chi phí LLM và Langfuse là theo dõi vận hành AI riêng, không thay thế F1.13. Giữ nguyên mã lịch sử trong các audit; chỉ liên kết bằng alias, không sửa dữ liệu/chứng cứ và không suy ra PASS. Quyết định này thống nhất mapping theo dõi, không tự phê duyệt pilot hay đóng bất kỳ gate nào.

PRD nêu **mục tiêu khởi điểm**, cần chốt trước khi đo: extraction F1 ≥85% từng nhóm; matching Macro-F1 ≥0.80; chuyên gia xác nhận đạt mandatory nhưng AI `NO_MATCH` ≤5%; NDCG@5 ≥0.75; và các mục tiêu quote, lỗi file, RBAC tại PRD. Thiếu dữ liệu/định nghĩa không được ghi PASS hoặc thay bằng kết quả synthetic.

## 3. Trình tự thực hiện đề xuất

### A. Hoàn thiện batch ba ưu tiên — có thể bắt đầu ngay trong code/test

**Đầu vào:** diff hiện có; không xóa hoặc reset công việc đang dở. Không có migration trong diff hiện tại.

1. Review lock ordering và hợp đồng API; bảo đảm confirm/cancel/execute/reopen, share/create feedback và các đường ghi liên quan được xét cùng thứ tự khóa. Kiểm tra lại cập nhật trạng thái job khi lỗi/đồng thời, idempotency và không lộ PII trong audit/error.
2. Thiết kế và review recovery cho **mất kết nối/crash/xóa storage một phần**: trạng thái bền vững/fencing, retry có chủ đích, cách chặn reopening/cancel khi còn tình trạng không chắc chắn, đối soát và thao tác phục hồi có kiểm soát. Quy định rõ chi phí vận hành/khóa kéo dài và tình huống không thể đảo ngược. Chỉ chọn cách triển khai sau review, không hứa atomic transaction với storage; nếu cần schema, dùng số migration trống kế tiếp sau khi kiểm tra local/remote, không sửa 00013 đã dùng.
3. Rà soát feedback chung, note, shares active/revoked/multi-candidate, feedback phát sinh sau purge và các share đã mất item do purge trước đây; đề xuất phương án fail-safe không làm mất dữ liệu của ứng viên khác. **HR/Privacy quyết định** xử lý dữ liệu chung; không tự xóa/sửa nội dung lịch sử.
4. Kiểm tra duplicate endpoint chỉ trả hai ứng viên cùng position, vai trò active HR phụ trách/HR Lead/Admin, HM/outsider/revoked bị từ chối; UI mô tả tín hiệu có thể cũ, không kết luận trùng và không có action merge/xóa/confirm/dismiss. Test dữ liệu thiếu/đổi và signal khác position.
5. Chạy backend unit + PostgreSQL/pgvector integration trên DB cục bộ dùng một lần hoặc CI; thêm test concurrency, crash/failure injection, retry, shared-feedback race và RBAC. Frontend i18n/unit/type-check/lint/build. Nếu thiếu kết quả integration, giữ `NOT VERIFIED`, không phát hành purge.
6. Ghi kết quả thật và giới hạn vào nhật ký Phase 1; tách commit có thể review, push đúng branch và chờ cả ba job CI xanh **khi người dùng đồng ý bước phát hành/đẩy code**. CI là test tự động, không phải E2E hay bằng chứng production.

**Done:** review/test integration qua, failure/recovery có cơ chế hoặc risk acceptance có thẩm quyền, tài liệu vận hành rõ; không tuyên bố DEP-02 PASS chỉ nhờ CI.

### B. Chuẩn bị gate có thể làm song song — chưa thao tác môi trường

- DevOps: điền inventory DEP-03/04/08, chủ sở hữu, topology worker, checklist key consumers, backup/restore/monitoring và rollback; chỉ lưu trạng thái, không lưu credential. Người có quyền kiểm tra branch protection.
- HR/Privacy/Legal: quyết định xử lý feedback share-level, retention scope/holds và phê duyệt egress; kiểm kê provider hồi cứu theo DEP-05.
- HR/HM/PO: xác nhận mapping Phase 1, tiêu chí pilot, policy scoring, đề xuất taxonomy nhãn và cách phân xử; chuẩn bị thiết kế/nguồn dữ liệu được phép, chưa thu thập/gửi CV thật khi chưa được duyệt.
- Kỹ thuật: gap analysis evaluation harness so với PRD; có thể chuẩn bị unit test/harness dữ liệu tổng hợp sau khi thống nhất contract, không tự khẳng định chất lượng model.

### C. Khi người dùng quyết định mở lại E2E — hiện đang dừng

1. Khóa phạm vi, owner, môi trường, SHA/migrations, preflight privacy và bằng chứng; xác minh chronology trước ký. Không lặp thao tác đã destructive/revoke chỉ để lấy lại bằng chứng.
2. Chạy E2E-02–04, rồi phần còn thiếu DEP-02 trên fixture mới tổng hợp (nếu được phê duyệt); đối soát API audit verify sau purge, database, storage và những mục có count trước xóa >0. Giữ E2E-13 partial nếu không đủ coverage.
3. Chỉ chạy E2E-14–16, UX usability và Langfuse staging nếu được đưa vào phạm vi, có quyết định môi trường/privacy riêng. Không coi bất kỳ `N/A` là PASS.
4. Chủ trì thu thập ký duyệt HR Lead/HM/IT theo phạm vi, đóng từng gate dựa vào bằng chứng chứ không theo tỷ lệ test.

### D. Sau điều kiện dữ liệu và vận hành

DEP-03/04/05 và DEP-08 theo chủ sở hữu; pilot quality theo bộ dữ liệu HR/HM đã duyệt. DEP-06 BGE sau endpoint/golden set/phê duyệt; DEP-07 LTR sau dataset/artifact/SHADOW. Các gate có thể chuẩn bị song song nhưng việc bật production chỉ sau điều kiện tương ứng; không suy đạt gate hoặc tự đổi cấu hình runtime vì có code hay smoke; lần đối chiếu trước ghi BGE control ON trên project test, LTR OFF.

## 4. Các hạng mục thảo luận dở ngoài Phase 1

| Hạng mục | Trạng thái / bước tiếp |
|---|---|
| F2.01/F2.02 Workflow Core | Plan đã lập nhưng **chưa duyệt**, D-01…D-10 chưa chốt. HR/HM/IT chốt taxonomy, ownership, level, scorecard, deadline/reminder và quyền trước schema/code. Số `00013` trong plan cũ đã được dùng cho direct approval; kiểm tra local/remote và chọn số tiếp theo khi bắt đầu. D-04 cần sửa để phản ánh cả direct approval đã được xác nhận, không vô tình xóa ngoại lệ hiện có. |
| UX-0…4 | Đã có code và CI cũ; usability HR/HM chưa được nghiệm thu. UX-5: global search, PDF highlight, pagination, retry từng file cần contract riêng; không dựng overall confidence chưa định nghĩa. |
| Langfuse | LF-1/LF-2A/LF-3A đã có code, mặc định tắt; đã ghi nhận smoke synthetic Cloud theo ảnh người vận hành, còn chờ kiểm chứng workflow thực và evaluation dataset. Chọn Cloud/self-host, mapping, retention, RBAC và privacy/egress; mặc định metadata-first, không gửi CV/JD/prompt. DEP-01 scoped không tự duyệt hạ tầng Langfuse. |
| F2.03/04/05/06/09 | Analytics/override, QA sampling, duplicate cross-position, OCR ảnh, compare/export cần quyết định và plan riêng; không suy diễn metric hoặc mở rộng quyền từ code hiện tại. |
| F2.07, SSO, rediscovery | Retention automation ngoài vòng này; SSO tạm treo; rediscovery theo quyết định phiên trước để cuối Phase 2, chờ consent/retention/quyền tái sử dụng. Không tự mở lại. |

## 5. Quyết định đã ghi và điểm gọi lại

- Người dùng đã đồng ý A1–A6, xác nhận HR/Privacy/Legal và DevOps đồng ý hướng xử lý liên quan; A4 chọn chỉ email/SĐT cùng vị trí cho Phase 1. Xem báo cáo tạm treo để phân biệt quyết định và bằng chứng triển khai.
- Phần B tạm treo để quay lại khi cần: kiểm tra thực tế môi trường, key, backup/restore, privacy và bộ pilot chưa được coi là PASS. E2E tiếp tục dừng; Phase 2 phần C chờ.
- Khi mở lại: dùng mapping F1.13 đã thống nhất, quyết định riêng về release/migration và E2E, xác nhận owner/bằng chứng từng DEP. Giữ direct approval, không tự bật BGE/LTR, SSO, F2.07 hay rediscovery.

Mọi trạng thái, commit, kết quả CI, quyết định phạm vi và bằng chứng thực tế phải được cập nhật trong `Update_Excute_P1.md`/`Update_Excute_P2.md` và checklist tương ứng khi phát sinh; không sửa lại các biên bản lịch sử để giả lập nghiệm thu.

### Đổi Hiring Manager sau khi tạo vị trí

HR phụ trách vị trí, HR Lead hoặc Admin có thể đổi HM tại chi tiết vị trí. HM được chọn phải có tài khoản ACTIVE và vai trò hệ thống HIRING_MANAGER; không được là người thực hiện hay HR đang phụ trách vị trí. Khi thực sự đổi, các phân công HM hiện tại và shortlist ACTIVE của những HM đó được thu hồi trong cùng giao dịch; shortlist ACTIVE còn sót của người được bổ nhiệm cũng bị thu hồi. Phản hồi, lịch sử duyệt và bản ghi chia sẻ được giữ. HM mới chỉ xem shortlist sau khi HR chủ động chia sẻ mới; bổ nhiệm lại HM cũ không khôi phục share đã thu hồi. Các quyền độc lập khác không tự thu hồi. Thao tác và các share bị thu hồi được ghi audit; phân công cũ được ghi trong metadata audit khi bản ghi phân công được tái sử dụng.

Duyệt tiêu chí đang chờ HM tiếp tục theo phân công mới; quyết định đã có không bị sửa. Nếu dữ liệu phân công thay đổi trong lúc mở hộp thoại, API trả 409 và người dùng cần đóng/mở lại để tải dữ liệu mới. Đổi HM bị chặn khi vị trí có case purge đang xử lý hoặc cần phục hồi. Chọn lại HM duy nhất đang phụ trách là no-op, không thu hồi share. Các kiểm thử cục bộ không thay thế E2E hay nghiệm thu môi trường đích.
