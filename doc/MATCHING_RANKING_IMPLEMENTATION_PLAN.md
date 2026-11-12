# Plan tiếp tục workflow Matching & Ranking

> **Trạng thái:** anh đã ưu tiên BGE/LTR, chọn khảo sát provider bên ngoài và duyệt batch chuẩn bị synthetic; kết quả/giới hạn ghi tại `doc/OFFLINE_MATCHING_SYNTHETIC.md`, khảo sát provider tại `doc/BGE_PROVIDER_PILOT_RESEARCH.md`. Duyệt này không đóng Phase 1/DEP, không cho phép dùng CV thật, deploy, bật runtime môi trường đích hay mở E2E. Phạm vi ở đây là workflow **matching/ranking theo từng vị trí**; không đồng nhất với plan Phase 2 F2.01/F2.02 vẫn đang chờ duyệt.
>
> Căn cứ: code `backend/app/services/matching.py`, `deterministic_matching.py`, `backend/app/workers/processor.py`, `evaluation.py`, các CLI đánh giá; `doc/MATCHING_STABILITY.md`, `doc/BGE_LTR.md`, `doc/HRA_PRD.md`, checklist E2E và báo cáo Phase 1. Những bằng chứng E2E đã ghi được nhắc lại để làm baseline, **không chạy lại**. Ngày trong một số bằng chứng lịch sử đang cần đối chiếu với đồng hồ/mốc thời gian của phiên trước khi ký phát hành.

## 1. Mục tiêu và phạm vi

1. Duy trì workflow CV → đối chiếu tiêu chí → bằng chứng → điểm/coverage → ranking cùng vị trí, minh bạch và HR quyết định.
2. Hoàn thiện **cách kiểm chứng độ ổn định và chất lượng**, trước khi khẳng định có thể dùng rộng hơn; phân biệt test giả lập, kết quả đo có nhãn và nghiệm thu môi trường đích.
3. Chỉ đề xuất thay hành vi thuật toán khi có defect hoặc dữ liệu chứng minh, có version/review và được duyệt. Không viết lại những phần đã có.
4. **BGE và LTR là ưu tiên của workflow** theo nhấn mạnh mới của anh: triển khai song song các phần chuẩn bị, đánh giá và khắc phục khoảng trống để đi tới pilot/SHADOW/ACTIVE có kiểm soát; không chờ hoàn tất mọi việc khác mới bắt đầu. Ưu tiên không đồng nghĩa đã duyệt endpoint, dữ liệu thật, E2E hay bật runtime. Các gate dữ liệu, privacy và vận hành vẫn giữ nguyên.

**Ngoài phạm vi plan này:** F2.01/F2.02 (vẫn chờ D-01…D-10), tự thay đổi trạng thái tuyển dụng, cross-position duplicate/rediscovery, retention automation, SSO, deploy hoặc chạy E2E. Công việc production/đánh giá dữ liệu thật tiếp tục theo `PHASE1_PRODUCTION_DEFERRED_REPORT.md` cho tới khi được mở lại có chủ đích.

## 2. Workflow nghiệp vụ cần giữ

1. **Tạo position/JD:** HR xác định vị trí, phiên bản JD và thành viên được phép. Một ứng viên được đánh giá trong bối cảnh một position, không xếp chung giữa các position.
2. **Criteria:** AI có thể đề xuất draft; HR chỉnh nội dung, nhóm và trọng số. Chỉ rubric đã được duyệt theo workflow hiện hành mới được dùng, gồm luồng dual approval và luồng direct approval của Admin/HR Lead đã được xác nhận. Không tự coi template/draft là approved.
3. **Nhận CV/profile:** HR upload PDF/DOCX; file xử lý lỗi cần HR xem, không tự loại. Trích xuất có version; khi JD/criteria/profile đổi, chỉ dùng assessment phù hợp snapshot hiện hành. Nội dung gửi model qua redaction best-effort, không coi là ẩn danh tuyệt đối.
4. **Matching:** rule dựa trên requirement spec và bằng chứng trước; LLM chỉ xử lý tiêu chí unresolved với các chunk liên quan. Kết quả từng tiêu chí là `STRONG_MATCH`, `MATCH`, `UNCLEAR`, `NO_MATCH`; quote phải được kiểm tra trong text đã trích xuất/redact, không xác minh được thì hạ về `UNCLEAR`. Bằng chứng hợp lệ về mặt vị trí chuỗi vẫn cần HR xét đúng ngữ nghĩa.
5. **Score và gate:** `matching-v2.1` loại `UNCLEAR` khỏi cả tử số và mẫu số điểm; nếu không tiêu chí nào scored, điểm `null`. Coverage là tỷ lệ trọng số có thể chấm, tách khỏi score; mandatory chưa rõ hoặc coverage thấp dẫn đến `NEEDS_HR_VERIFICATION`. Mandatory `NO_MATCH` có bằng chứng có thể dẫn tới `POSSIBLE_MISMATCH`; không được đánh đồng thiếu dữ liệu với không đạt.
6. **Ranking:** hiện sắp theo status → score giảm dần → coverage giảm dần → application ID. Hiện code gán `rank_number` nếu coverage ≥ ngưỡng và status khác `NOT_ASSESSED`; do đó `NEEDS_HR_VERIFICATION` hoặc `POSSIBLE_MISMATCH` **có thể vẫn có số hạng** khi đủ coverage. Đây là thứ tự hỗ trợ rà soát, không phải kết luận đủ điều kiện tuyển. Có nên ẩn số hạng cho mọi hồ sơ cần xác minh/mismatch là quyết định M-D01 bên dưới; không tự đổi.
7. **HR quyết định:** UI hiển thị kết quả từng tiêu chí, điểm một phần, coverage, status và dẫn chứng. HR kiểm tra, chuyển trạng thái và chia sẻ shortlist theo quyền; điểm/AI không tự shortlist, loại hoặc thay đổi trạng thái.
8. **Truy vết:** assessment/ranking gắn các version, nguồn và fingerprint. Cùng fingerprint hoàn tất được reuse; fingerprint bao gồm evaluation date, nên thay ngày cũng có thể làm fingerprint khác. Không sửa đè kết quả cũ.

### Quy ước cụ thể đã chốt

- Giữ yêu cầu Python **ít nhất 4 năm**; `partial_backend` ghi 2 năm → `UNCLEAR` để HR xác minh, không tự `MATCH` hay `NO_MATCH`. Không sửa `staging/synthetic/manifest.json` hoặc silently đổi kỳ vọng.
- Duplicate Phase 1: chỉ cảnh báo exact email/SĐT trong cùng vị trí, không tự gộp/xóa; không yêu cầu detector nội dung file cho phạm vi đã chốt.
- DM-01/DM-02 đã đóng theo bằng chứng trước; known variance của fixture đã được chấp nhận. E2E-05/06/07/08 có PASS theo checklist cho phạm vi synthetic đã chạy, không chứng minh quality pilot. DEP-01 `CLOSED_SCOPED`, DEP-02 partial.

## 3. Ưu tiên mới: hai luồng BGE và LTR chạy song song

Ghi nhận ý định ưu tiên sử dụng BGE/LTR để nâng chất lượng, thay cho cách diễn đạt trước đó coi đây chỉ là hướng chuẩn bị sau M3. Chưa coi đây là quyết định bỏ gate hay mở lại E2E/phần B toàn bộ.

- **BGE:** ưu tiên tìm bằng chứng CV phù hợp hơn cho các criterion mà deterministic rules chưa kết luận; code hiện tại không dùng BGE để trích xuất toàn bộ CV, trực tiếp chấm điểm hay thay kết luận rules. Chất lượng OCR/extraction vẫn phải đo và cải thiện riêng nếu có defect. Không hứa chắc BGE tăng chất lượng nếu chưa đo.
- **LTR:** ưu tiên cải thiện thứ tự trong phạm vi status/coverage gate, dựa trên features của assessment; SHADOW không thay thứ tự chính thức. Không thay AI thành quyết định tự loại/shortlist và không đổi rule rank hiện tại nếu chưa duyệt.
- **Luồng chung ngay từ đầu:** M0 contract và M1 evaluator cùng M2 chuẩn bị contract nhãn. Song song thiết kế harness BGE và LTR, test synthetic, kiểm tra privacy/endpoint/dataset. BGE và LTR không phải đợi nhau; chốt feature/semantic version tại mỗi lần train/đánh giá LTR, và đánh giá lại nếu đầu vào BGE/matching thay đổi.
- **Điểm dừng:** pilot bằng model thật/call provider, dùng dữ liệu thật, deploy, chạy E2E, bật SHADOW/ACTIVE tại môi trường đích phải có phạm vi và phê duyệt riêng thích hợp. Chuẩn bị local synthetic không tự đóng DEP-05/06/07.

### Gate và việc cụ thể cần thêm vào plan

| Gate/việc | Còn thiếu hoặc cần xác minh | Người phối hợp và bằng chứng |
|---|---|---|
| G1 — phạm vi và môi trường | Chọn isolated local/dev hay staging cho thử model; xác nhận runtime/commit, schema `00010/00011`, endpoint/model và topology thực tế khi tiến tới môi trường đích. Không suy production đã chạy đúng từ code hay migration lịch sử. DEP-03/08 áp dụng theo phạm vi. | Anh/PO + DevOps; scope, config không lộ secret, snapshot baseline, rollback và preflight. E2E vẫn tạm treo. |
| G2 — privacy/DEP-05 | Kiểm kê hồi cứu LLM/gateway đã dùng; với dữ liệu thật đánh giá toàn bộ LLM/BGE/OCR, nguồn dữ liệu, quyền, vị trí xử lý, egress, provider retention/training/deletion, log, redaction và vector/cache. Redaction best-effort, vector/ID vẫn có thể nhạy cảm; self-host không tự miễn privacy. | IT Security/Privacy/Legal + HR; phê duyệt cho đúng loại dữ liệu, provider và môi trường. Không ghi secret/CV thật vào repo. |
| G3 — endpoint BGE | Chốt BGE-M3 self-host hoặc provider, ngân sách/quota, model ID, instruction query/document, API tương thích `/embeddings`, 1024 chiều, độ ổn định và deadline/timeout. Endpoint Cloudflare nêu trong doc cũ chỉ là lựa chọn cần kiểm chứng lại điều khoản/chi phí; không ngầm chọn hay cam kết sẵn dùng. | IT/DevOps; test contract bằng dữ liệu synthetic sau khi được phép, đo latency/limit và fallback. Provider `hash` chỉ test plumbing, không phải BGE. |
| G4 — gold data chung | Nhãn bằng chứng/criterion cho BGE và relevance theo position cho LTR, nguồn hợp pháp, blind review, adjudication, phiên bản JD/rubric/profile, tách holdout theo position và theo thời gian khi khả thi, chống trùng ứng viên/leakage. | HR/HM + Privacy; dataset version, label rubric, reviewers, provenance và báo cáo phân bố/missing. Công việc thật chỉ sau phê duyệt tương ứng. |
| G5 — BGE DEP-06 | Harness lexical vs BGE trên cùng cohort/holdout: evidence Recall@5, false MATCH/NO_MATCH, unresolved, quote validity, latency/cost/error/fallback. Chốt độ cải thiện tối thiểu và ngưỡng không suy giảm trước khi đo, bao gồm slice tiếng Việt/Anh và họ vị trí; hiệu chỉnh top-k/similarity trên calibration, không dùng holdout để tune. | HR + QA/Backend; báo cáo số mẫu/denominator, thông số model/index và go/no-go. Không khẳng định model tăng chất lượng từ plumbing synthetic. |
| G6 — LTR DEP-07 | Có HR gold (không dùng weak label thay gold); offline group-holdout và gate, quản trị artifact, báo cáo SHADOW + monitoring. CLI mặc định ≥200 examples/10 groups, holdout ≥20 examples/2 groups, NDCG@10 ≥0.70, pairwise ≥0.65; giữ holdout tách position dù rubric version thay đổi. | HR/HM + Backend; dataset/label report, metrics theo nhóm, artifact hash/review. Registry `APPROVED` và gate đạt là cần thiết khi xét ACTIVE, nhưng chưa đủ nếu thiếu SHADOW/ops. |
| G7 — rollout/rollback | Kiểm tra thất bại provider/pgvector/cache; visibility của `ltr_score` trên API/UI trong SHADOW; model load/hash fail-closed; log/metrics/alerts, cấu hình theo worker và khả năng giới hạn pilot thực tế. Nếu không tách được phạm vi, không gọi rollout là giới hạn. | DevOps/QA/HR; preflight, monitoring, chủ sở hữu và rollback semantic OFF/LTR OFF, lưu snapshot lịch sử. |

**Các hạng mục nên triển khai trong batch chuẩn bị synthetic sau khi anh duyệt:** (1) evaluator so sánh snapshot thực và fail-closed khi thiếu mẫu; (2) retrieval benchmark & test lỗi endpoint/pgvector/cache/evidence; (3) dataset/label contract + validator/merge HR gold chống nhầm snapshot, không bắt buộc xây UI; (4) SHADOW report đối chiếu baseline và thứ tự giả định ACTIVE theo từng position/status/coverage, test gate bằng fixture. Chỉ tạo framework và dữ liệu giả lập: không phát biểu đã chạy BGE thật hoặc có model LTR đạt gate.

## 4. Đã có gì / còn thiếu gì

| Hạng mục | Hiện có | Cần làm/giới hạn |
|---|---|---|
| Baseline | rules `deterministic-rules-v1.4`, `matching-v2.1`, `ranking-v2.0`; versioned snapshot, scoring, evidence, UI breakdown/điểm một phần. | Không triển khai lại; regression sau mọi thay đổi. Runtime môi trường đích phải xác nhận riêng trước release. |
| Độ ổn định | `evaluation.py`, `evaluate_matching.py`, exporter snapshot; metrics drift, criterion flip, Kendall/overlap. | Chưa phải công cụ đánh giá đúng/sai bằng nhãn HR. **Lưu ý:** fallback ranking của CLI sắp score/coverage, không áp mandatory status; exporter không cung cấp đầy đủ cặp baseline/candidate, và khi không có position filter có thể lấy run mới nhất toàn cục. `--check` hiện có thể bỏ qua reuse khi không có stats và coi ranking thiếu metric là ổn. Không dùng kết quả thiếu dữ liệu để ký PASS; cần siết contract/báo cáo trước nghiệm thu. |
| Chất lượng pilot | PRD nêu mục tiêu khoảng 300 cặp CV–JD–rubric, tối thiểu đề xuất 200; HR/HM gán nhãn và phân xử. | Chưa có bộ gold được xác nhận/được phép và báo cáo các metric; các fixture tổng hợp không thay thế. Con số trong tài liệu stability 50–100 CV là gợi ý xây golden set riêng, không tự thay mục tiêu PRD hoặc coi một CV là một cặp. |
| BGE | Có provider/pgvector/fallback; `hash` để plumbing, không phải BGE. | Chờ endpoint phù hợp, phê duyệt, golden set và đánh giá retrieval; không bật production. |
| LTR | Có `OFF/SHADOW/ACTIVE`, training, registry/approval và artifact hash; F-01 fail-closed đã sửa. | Chưa có HR gold dataset/SHADOW report đủ điều kiện; exporter label theo trạng thái chỉ là weak label. Không dùng weak label để tuyên bố ACTIVE. |
| Workflow HR–HM mở rộng | Share/feedback hiện tại có; direct approval đã có. | F2.01/F2.02 rubric library/scorecard là batch riêng, plan và D-01…D-10 chưa duyệt; không tự triển khai dưới tên matching. |

## 5. Các batch đề xuất

### M0 — Khóa baseline và contract (có thể làm cục bộ, không thay output)

**Việc làm**
- Lập bảng input/output/version, các trường hợp có rank/không rank, cách hiển thị trạng thái/coverage/quote và quyền HR/HM; rà mapping F1.13 (pilot evaluation so với dashboard/worker) với PO.
- Kiểm tra regression: Python 4 năm/partial 2 năm, thiếu bằng chứng vs `NO_MATCH`, quote sai/trang sai, trọng số, coverage sát 0.70, profile/JD/rubric mới và ranking cùng position; giữ nguyên manifest.
- Xác định baseline theo commit, cấu hình và bộ dữ liệu **synthetic**; metadata không chứa secret/CV thật. Không sửa kết quả E2E lịch sử.

**Hoàn tất:** tài liệu contract + test tự động chạy trên repo/DB test dùng một lần; không thay semantics hoặc tuyên bố quality. Cần M-D01 nếu muốn thay rank eligibility.

### M1 — Củng cố harness repeatability/ranking (đề xuất batch code đầu tiên)

**Đầu vào:** M0; synthetic snapshots. Chỉ làm sau khi duyệt plan/ưu tiên batch.

- Thiết kế đầu vào so sánh **baseline/candidate tường minh** theo position + criteria version + cohort/run/version; yêu cầu không trộn vị trí, version hoặc application khi xác định ranking. Dùng ranking run snapshot thực tế, không mặc định tự sắp score thay cho mandatory gate.
- Tách phép đo **reuse cùng fingerprint** khỏi phép đo **forced rerun có kiểm soát**. Định nghĩa cohort tương đương cho rerun có fingerprint khác (bao gồm evaluation date/model/config), không xóa/ghi đè assessment thật để ép chạy lại.
- `--check` cho mục đích nghiệm thu phải báo **INSUFFICIENT_DATA / không đạt gate** nếu thiếu baseline/candidate, reuse denominator, đủ item để tính metric hoặc metric không xác định; không biến `null` thành PASS. Giữ chế độ diagnostic tương thích nếu cần nhưng không gọi đó là acceptance.
- Báo cáo các population missing/extra, unranked/ties, số so sánh và denominator; không tính lẫn unranked như ranked. Mỗi flip mandatory/`NO_MATCH` phải có hàng đợi review HR.
- Regression tests: hai position có score tương tự nhưng status khác, missing status/rank, fingerprint khác ngày, kết quả thiếu, ties/top-k nhỏ, no-reuse stats, duplicate IDs và boundary 70%.

**Đầu ra:** CLI/report có định nghĩa rõ, test unit + PostgreSQL integration dùng một lần + CI; chỉ dữ liệu synthetic. Không đổi ranking runtime, LLM prompt hay BGE/LTR. **Không tự đánh giá model thật hay chạy E2E.**

### M2 — Contract đánh giá chất lượng và nhãn (thiết kế có thể chuẩn bị; dữ liệu thật đang treo)

- HR/HM/Privacy/IT quyết định nguồn CV/JD/rubric được phép, consent, nơi lưu, thời hạn/xóa, quyền; không lưu CV thật/nhãn có thể tái định danh trong Git hay log. ID giả danh vẫn là dữ liệu có thể tái định danh.
- Định nghĩa `dataset_version`, position/JD/criteria/profile/assessment snapshot, criterion, nhãn gold 4 mức, reviewer, timestamp và adjudication; mẫu gán nhãn độc lập không hiển thị score/rank AI để giảm bias. Audit không chứa quote/PII; quote gốc chỉ lưu nơi được phép.
- Chốt đơn vị mẫu, phân bố nhóm vị trí, 200–300 **cặp CV–JD–rubric** là mục tiêu PRD; CV, application, criterion finding và ranking group là đơn vị khác nhau. Tách calibration và holdout theo position/đợt, xử lý hồ sơ lặp để tránh leakage; ghi cách lấy mẫu, missing và phân xử.
- Xây metric contract trước khi làm harness: confusion matrix/macro-F1 4 mức theo criterion; false negative mandatory `gold đạt` nhưng AI `NO_MATCH` với mẫu số rõ, báo riêng `UNCLEAR`; false MATCH; unresolved; độ đúng quote trên mẫu; extraction F1 theo trường; NDCG@5 trong từng position/rubric với nhãn relevance đã duyệt. Báo coverage, sample size và kết quả theo nhóm, không chỉ số tổng.
- Mục tiêu khởi điểm theo PRD: extraction F1 ≥0.85 từng nhóm, matching macro-F1 ≥0.80, false negative mandatory ≤5%, NDCG@5 ≥0.75; các ngưỡng là mục tiêu cần HR/HM/PO chốt trước lần đo, không nâng/hạ sau khi thấy kết quả. Dữ liệu ít hơn tối thiểu đề xuất chỉ tham khảo.

**Hoàn tất:** specification + test tính metric trên dữ liệu synthetic và báo thiếu dữ liệu; chưa gọi là model đạt hay pilot đạt. Thu thập/dùng dữ liệu thật chỉ sau quyết định riêng và các gate phù hợp.

### M3 — Đánh giá baseline và xử lý defect (đang chờ mở lại phần B)

1. Sau khi có dữ liệu được phép, owner, phạm vi và preflight, khóa dataset/holdout/version trước chạy; đo baseline rules v1.4/score v2.1/ranking v2.0.
2. Xuất báo cáo per-position/per-criterion và nhóm IT; review từng false mandatory/NO_MATCH, quote sai, sai extraction, thiếu bằng chứng; ghi defect, mức độ, owner và nguyên nhân.
3. Đề xuất bản sửa **từng defect**, bump version rules/prompt/policy tương ứng; chạy test + tập calibration, rồi holdout độc lập; giữ snapshot cũ, không chỉnh nhãn hoặc ngưỡng để hợp thức hóa.
4. HR/HM/PO review các sai lệch; quyết định đạt/không đạt hoặc chấp nhận giới hạn bằng văn bản. Không tự chạy E2E/staging hoặc bật model mới khi chưa được phép.

### M4 — BGE semantic pilot (DEP-06; đang chờ)

- Điều kiện: môi trường được duyệt, DEP-05 theo phạm vi, endpoint BGE 1024 chiều/token/quota và golden set HR; dữ liệu thật chỉ theo phê duyệt. Không coi `hash` hay đề xuất endpoint ở tài liệu cũ là phê duyệt dùng provider.
- So sánh lexical baseline với BGE trên cùng holdout: Recall@5 cho chunk bằng chứng, false MATCH/NO_MATCH, unresolved, latency, lỗi/fallback; test evidence verification và cache/index version. Semantic chỉ bổ sung chunk cho LLM fallback, không được tự thay outcome deterministic.
- Chốt go/no-go với HR/IT/Security, rollback semantic OFF và ghi version index/model; thay model/dimension cần đánh giá tương thích schema. Chỉ chạy sau khi gate được mở.

### M5 — LTR offline → SHADOW → cân nhắc ACTIVE (DEP-07; đang chờ)

- Chuẩn bị HR gold labels độc lập, assessment/rubric snapshot và leakage control. Đề xuất gán nhãn blind/adjudication; chưa chọn UI mới nếu chưa được duyệt.
- Train offline group-holdout; CLI có ngưỡng mặc định 200 examples/10 groups, holdout ≥20 examples/2 groups, NDCG@10 ≥0.70 và pairwise ≥0.65. Đây là gate LTR riêng, **khác** NDCG@5 mục tiêu pilot PRD; không hạ gate chỉ để qua.
- Đăng ký artifact `DRAFT`, review dataset/hash/metrics, Admin approve theo governance. SHADOW chỉ ghi điểm, không thay thứ tự công bố. Xây report so sánh theo từng position/version/gate, overlap, rank shifts và 0 vi phạm mandatory/coverage; chốt số lượt/chu kỳ đại diện trước khi xem kết quả.
- ACTIVE chỉ xét sau HR/IT phê duyệt dataset, artifact, SHADOW, monitoring và rollback; LTR chỉ reorder trong status và coverage gate, không qua gate nhờ score. BGE không bắt buộc chạy trước LTR, nhưng thay BGE/rule/policy làm thay distribution nên phải đánh giá lại artifact.

### M6 — Release và nghiệm thu (chờ quyết định môi trường)

- Bật lại phần B phù hợp: DevOps xác nhận topology/mixed-version/drain, key/JWT, backup/restore, monitoring và môi trường; Privacy/Legal xác nhận egress/retention theo phạm vi.
- Khi anh mở E2E trở lại, khóa scope trước chạy; dùng synthetic và kiểm tra E2E-02–04/DEP-02 theo kế hoạch riêng, không lặp thao tác xóa/thu hồi cũ. Usability HR/HM, OCR/BGE/worker recovery chỉ khi được đưa vào scope và có điều kiện tương ứng.
- Ghi commit/migrations/config không lộ secret, bằng chứng, defect và chữ ký vai trò; chỉ đóng gate đúng phạm vi. Review rollback và không tuyên bố Phase 1/production pass từ CI hoặc smoke.

## 6. Thứ tự, owner và ước lượng sơ bộ

| Chặng | Phụ thuộc | Owner đề xuất | Công sức kỹ thuật sơ bộ* | Điểm dừng |
|---|---|---|---|---|
| M0 | Anh duyệt batch, M-D01 | Backend + HR/PO review | 1–2 ngày | Chốt baseline/contract; không sửa policy ngầm |
| M1 | M0 | Backend/QA | 3–5 ngày | Report synthetic đủ dữ liệu, test/CI pass; chưa gọi là quality thực |
| M2 thiết kế | M0; có thể song song M1 | HR/HM + QA/Privacy | 2–4 ngày kỹ thuật, chưa tính thời gian HR | Chốt metric/nhãn; không thu thập dữ liệu thật |
| M3 | M2, dataset có phép, phạm vi B được mở | HR/HM + Backend/QA | Chưa ước lượng đáng tin cậy | Chỉ đề xuất sửa defect sau baseline review |
| M4 | DEP-05/06, endpoint + gold | IT/Security + HR/Backend | Chưa ước lượng đáng tin cậy | BGE OFF đến khi có quyết định riêng |
| M5 | DEP-07, gold, artifact + review | HR/HM + Backend/ML | Chưa ước lượng đáng tin cậy | SHADOW không đổi ranking; ACTIVE cần duyệt riêng |
| M6 | Các gate liên quan và anh mở phạm vi môi trường/E2E | DevOps + QA + HR/PO | Theo phạm vi được duyệt | Go/no-go, rollback, không tự đóng gate khác |

\* Ước lượng để lập thứ tự, không phải cam kết lịch; phụ thuộc người review, tình trạng môi trường và kết quả audit. M3–M6 có thể kéo dài vì dữ liệu/duyệt, không nên gộp thành một mốc release. M4 và M5 độc lập tương đối, không cần đợi nhau nhưng phải đánh giá lại khi baseline đầu vào thay đổi.

## 7. Tiêu chí chất lượng và an toàn xuyên suốt

- Không dùng score để tự reject/shortlist; không thay đổi `UNCLEAR` thành `NO_MATCH` vì thiếu dữ liệu. Python 2 năm vẫn là case kiểm thử HR review, không thay manifest.
- Mỗi criterion có tối đa một finding; evidence không xác minh phải `UNCLEAR`; HR kiểm tra ngữ nghĩa và tình huống phản chứng. Độ phủ dưới 70% không được xem là ranking ổn định.
- Ranking cùng position và đúng rubric/profile hiện hành; không đưa hồ sơ thiếu assessment hợp lệ vào ranking như thể đã đánh giá.
- Regression cho quyền truy cập/ẩn HR notes, snapshot cũ khi sửa hồ sơ, thay version, reuse, tái xử lý và hành vi lỗi provider; CI PostgreSQL dùng một lần, không chạy integration suite trên Supabase thật.
- Theo `MATCHING_STABILITY.md`, ngưỡng stability tham khảo: reuse 100% khi eligible; P95 drift ≤2 điểm, criterion flip ≤2%, Kendall/Top-10 ≥0.90. Chỉ đánh giá khi đủ dữ liệu/denominator và cùng cohort có ý nghĩa; mọi mandatory flip/`NO_MATCH` cần HR review. Các ngưỡng này **không** chứng minh model đúng hoặc thay thế pilot gold.
- PII/evidence/candidate IDs và metadata có thể nhạy cảm: phân quyền, lưu ngoài Git, xóa theo policy; logs/CI chỉ dữ liệu tổng hợp giả lập, không ghi credential.

## 8. Quyết định cần anh duyệt trước khi code

| Mã | Câu hỏi | Đề xuất để anh chọn |
|---|---|---|
| M-D01 | Số hạng cho `NEEDS_HR_VERIFICATION`/`POSSIBLE_MISMATCH` khi coverage ≥70%? | **Giữ nguyên hành vi hiện tại** ở batch đầu, hiển thị rõ cần HR rà soát; nếu muốn luôn bỏ rank với các trạng thái này, duyệt riêng policy/ranking version và test/đánh giá tác động. |
| M-D02 | Ưu tiên code? | M0 + M1 song song chuẩn bị harness/contract BGE/LTR (synthetic/unit/integration/CI); M2 contract nhãn, chưa thu CV thật. Duyệt phạm vi batch chuẩn bị riêng. |
| M-D03 | Chọn hướng BGE và mở phạm vi thử nghiệm nào? | Chọn self-host hoặc provider (chưa cần gửi credential); chọn môi trường isolated và dữ liệu synthetic cho pilot model thật. Để dùng CV thật hay bật runtime môi trường đích cần duyệt riêng; DEP-05/06/07 vẫn là gate, mở lại phần B có chọn lọc theo phạm vi được duyệt. |
| M-D06 | Nguồn gold và người phối hợp? | Anh chỉ định HR/HM và Security/Privacy/DevOps phụ trách chuẩn bị label/gate; chốt số lượng, quyền và tiêu chí nhãn trước khi dùng dữ liệu thật. |
| M-D07 | SHADOW/ACTIVE? | Sau khi có kết quả và gate riêng, đề xuất phạm vi, thời gian, tiêu chuẩn go/no-go và rollback để anh duyệt; không bật chỉ vì ưu tiên BGE/LTR. |
| M-D04 | E2E? | Tiếp tục treo; khi mở lại khóa phạm vi riêng. |
| M-D05 | F2.01/F2.02? | Vẫn chờ plan và D-01…D-10; không coi plan matching là phê duyệt Workflow Core. |

Không có thay đổi code, schema, cấu hình runtime, deploy, test E2E hoặc dữ liệu môi trường chỉ vì plan này được lập.
