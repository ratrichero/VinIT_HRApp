# Batch chuẩn bị matching/BGE/LTR bằng synthetic

## Phạm vi và giới hạn

Các công cụ đọc JSON cục bộ, không kết nối DB/provider, không tạo assessment hay ranking thật, không thay đổi runtime. Fixture tại `staging/synthetic/offline_matching/` hoàn toàn bịa đặt: hai JD, bốn CV ngắn và snapshot/score/label minh họa tự tạo; ID không đại diện người thật. Không sửa `staging/synthetic/manifest.json`. Fixture ít và có tương quan dựng sẵn chỉ để kiểm thử plumbing, **không phải HR gold, không đủ đo chất lượng BGE/LTR**, không dùng để đóng DEP-05/06/07, pilot hoặc production.

Không upload CV/JD thật, credential hay dataset có thể tái định danh vào Git, issue, log hoặc CI. Bộ công cụ không tự chứng minh privacy, nhãn là thật hay provenance đúng.

## Chạy tại repo

```bash
PY=backend/.venv/bin/python
DATA=staging/synthetic/offline_matching
$PY backend/scripts/offline_matching_eval.py repeatability $DATA/repeatability_example.json --check
$PY backend/scripts/offline_matching_eval.py retrieval $DATA/retrieval_example.json
$PY backend/scripts/offline_matching_eval.py shadow $DATA/shadow_example.json
$PY backend/scripts/offline_matching_eval.py labels $DATA/labels_example.json
```

Không có network hay DB. `--check` chỉ dùng cho repeatability; exit 0 là đạt ngưỡng trên input cung cấp, 2 là FAIL, INSUFFICIENT_DATA hoặc input lỗi. Ba mode còn lại là diagnostic/kiểm tra cấu trúc, không có nút PASS model. Legacy `evaluate_matching.py` vẫn xuất diagnostic cũ nhưng `passed=false`, `acceptance_status=INSUFFICIENT_DATA`; `--check` luôn exit 2. Library cũ và push Langfuse vẫn là phép tính diagnostic; tuyệt đối không coi boolean cũ là acceptance.

### Repeatability

Xem JSON fixture để biết contract: `baseline`/`candidate` gồm position, criteria version, cohort, ranking run và policy version, coverage threshold, assessments và danh sách `ranked_application_ids` theo đúng thứ tự **snapshot thực**, `unranked_application_ids` tách riêng; mỗi assessment cần ID, fingerprint, `comparison_input_id`, status, score/coverage và kết quả/catégory từng criterion. `reuse` chứa số eligible/reused từ phép thử reuse độc lập.

- Phải có **hai assessment ID và ranking run ID khác nhau**, cùng input comparison ID, cùng position/rubric/cohort/policy/threshold; cùng criterion/category. Điều này không tự chứng minh forced rerun — operator phải chứng minh input/config/date và run thực đã được kiểm soát.
- Không tự suy ranking theo score và không xem unranked là ranked. Nếu cohort thiếu/extra, thiếu score, reuse không hợp lệ, tập ranked đổi, hoặc có dưới 10 hồ sơ ranked thì không ký PASS; input sai contract trả lỗi. Ties không được biểu diễn bằng list ID; không dùng cho snapshot có tie thật.
- `fingerprints_changed` liệt kê thay đổi (ngày đánh giá có thể thay fingerprint); không suy thay fingerprint là cùng nội dung. Mọi `mandatory_review` cần HR review dù report PASS. Số lượng/threshold trong code chỉ đo điều kiện kỹ thuật, không là bằng chứng chất lượng thực, tính đại diện hay chất lượng provenance.
- Exporter cũ không đủ hai snapshot/metadata theo contract mới. Việc dựng/export paired snapshots đáng tin cậy từ DB là **việc còn lại**, chưa có; không gán `comparison_input_id` giả để làm PASS.

### Retrieval

Mỗi case khai báo tập chunk thuộc tài liệu, tập gold không rỗng, candidate lexical và `semantic_candidates` với cosine score. Các candidate semantic là đầu vào đã retrieve/top-k; công cụ dùng `merge_candidate_chunks` thực tế để lấy tối đa năm chunk. Báo micro Recall@5 = tổng gold chunks được tìm thấy / tổng gold chunks; hit rate = số query có ít nhất một gold được tìm / số query. Không có gold thì không đánh giá được; kết quả phải cùng cohort.

Fixture là điểm semantic **tự đặt**, không phải inference BGE. Tool chưa gọi provider hoặc tự sinh embedding, chưa tự đo latency/cost, false outcome/quote hay slice; các việc này còn lại trước DEP-06. Khả năng tìm lại chunk không chứng minh LLM kết luận đúng.

### LTR shadow

Snapshot có assessment và `ltr_score` cho từng hồ sơ. Tool kiểm tra published list khớp policy SHADOW cục bộ, dùng `MatchingEngine.rank_applications` tính thứ tự ACTIVE giả định, báo thay đổi thứ tự, Kendall/top-k và kiểm tra status/coverage gate. Chỉ mô phỏng: **không load/approve artifact, không chạy SHADOW runtime và không tính NDCG trên gold**. Ngưỡng coverage snapshot phải khớp cấu hình local; chưa chứng minh model load/hash, chất lượng hay khả năng rollout. Snapshot nhóm không trộn position/rubric; ranked và unranked phải khớp eligibility.

### Label contract

`labels` kiểm tra dataset version, `SYNTHETIC` hoặc `HR_GOLD`, position/rubric/application/assessment/reviewer/time, label 0–3, trạng thái agreement/adjudication và đủ các field feature LTR hiện tại. Không chấp nhận `WEAK` làm gold; một position không được nằm ở nhiều group. Validator **không xác minh** reviewer có thật, quyền/consent, timestamp, nhãn, snapshot join hay trùng ứng viên giữa position. Tệp mẫu chỉ có `SYNTHETIC`, không đủ train và không được thay source thành HR_GOLD để qua gate. Chưa có UI/API nhãn HR hay validator/merge DB đáng tin cậy.

## Gợi ý dataset synthetic mở rộng (nếu nhờ agent khác)

- Chỉ sinh dữ liệu hư cấu rõ ràng: tên/email `@example.test`, không dựa trên CV/JD thật; không gán danh tính HR hay nhãn HR thật. Không dùng dữ liệu này để huấn luyện artifact production.
- Đề xuất 10–15 position IT, mỗi position 15–25 CV độc lập, 2–5 tiêu chí: IT backend, data, QA, frontend, vận hành; tiếng Việt/Anh và CV song ngữ. Có `dataset_version`, ID position/criteria/application, nội dung JD/CV, label giả lập và lý do/quote trỏ vào CV.
- Phủ đủ thiếu bằng chứng, skill đồng nghĩa, kinh nghiệm định lượng 2/4/5 năm với Python tối thiểu 4 năm, không năm, role không liên quan, skill phủ định, ngày trùng, CV dài/ngắn và trường hợp nhiều chunk. Không đánh đồng thiếu evidence với `NO_MATCH`; không sửa manifest hiện có.
- Tách train/calibration/holdout theo **position**, kiểm tra CV trùng giữa các tập; labels và quote phải được kiểm tra nhất quán. Không tự đưa case mô phỏng thành gold hay thay thế HR adjudication.
- Các format PDF/DOCX/OCR là phạm vi đánh giá extraction riêng và cần sinh/kiểm tra an toàn; batch hiện tại chỉ có text. Các E2E vẫn treo tới quyết định riêng.
