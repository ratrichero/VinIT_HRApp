# Báo cáo phạm vi công việc tạm treo — Phase 1 trước vận hành thực tế

> Theo xác nhận của người dùng trong phiên làm việc: các việc thuộc phần B được khoanh vùng, ghi lại và **tạm treo để quay lại khi cần**. Đây là báo cáo tồn đọng, không phải bằng chứng kiểm tra, phê duyệt triển khai hay đóng các DEP. Ngày/mốc bằng chứng lịch sử cần được đối chiếu trước ký nghiệm thu vì repository đang có mốc thời gian không thống nhất với ngày hệ thống của phiên.

## 1. Những quyết định đã xác nhận trong phạm vi A

Người dùng xác nhận đồng ý A1–A3 và cho biết HR/Privacy/Legal cùng DevOps xác nhận các hướng xử lý này; không có danh tính/chữ ký riêng hay biên bản kỹ thuật đính kèm. Ghi nhận theo đúng phát biểu, **không suy ra đã xác minh thực tế các kiểm soát phần B**.

- **A1:** Dừng purge khi share đang liên kết có note hoặc feedback chung; HR/Privacy rà soát, không tự sửa/xóa nội dung chung của nhiều ứng viên.
- **A2:** Sau purge, không nhận feedback chung mới trên share cũ; HR có thể tạo share mới cho hồ sơ còn lại. Các văn bản tự do khác vẫn có thể nhắc đến ứng viên đã xóa; lịch sử trước guard không tự được chứng minh là sạch.
- **A3:** Khi kết quả xóa storage không chắc chắn, không tự retry; DevOps xác nhận executor/request cũ dừng và đối soát trước khi HR Lead/Admin có quyền quyết định tiếp tục xóa thủ công theo `RETENTION_RECOVERY_RUNBOOK.md`. Không khẳng định DB/storage là atomic.
- **A4:** Chấp nhận phạm vi duplicate Phase 1 chỉ email/SĐT exact trong cùng vị trí; **không yêu cầu phát hiện trùng nội dung file để đóng phạm vi Phase 1 này**. Không tự merge/xóa hay cross-position. Đây là chấp nhận giới hạn phạm vi, không chứng minh detector hoặc toàn Phase 1 đã nghiệm thu.
- **A5:** Giữ Python tối thiểu 4 năm; `partial_backend` ghi 2 năm → `UNCLEAR`, HR xác minh; không thay manifest hay tự chuyển `MATCH`/`NO_MATCH`.
- **A6:** E2E tiếp tục tạm treo. Nếu mở lại, phải có quyết định mới về phạm vi/môi trường/lịch và không tự lặp thao tác destructive đã chạy.
- **C:** F2.01/F2.02 và quyết định D-01…D-10 tiếp tục chờ; không suy ra phê duyệt Phase 2.

## 2. Danh mục B — tạm treo, cần mở lại có chủ đích

| Nhóm | Phạm vi cần xử lý khi mở lại | Chủ trì dự kiến | Bằng chứng/điều kiện tối thiểu |
|---|---|---|---|
| B1 — Deployment/topology (DEP-03) | Xác nhận môi trường, runtime/commit, PM2/backend/worker, số instance, kết nối DB, drain mixed-version, migration/rollback và thời điểm release. | DevOps/Release | Mapping môi trường thực tế, phiên bản, cửa sổ và kế hoạch rollback được phê duyệt; lần đối chiếu trước đã thấy project test có migration đến `00022`, gồm `00014`; vẫn cần xác minh môi trường đích, runtime và rollback khi mở lại. |
| B2 — Key/JWT (DEP-04) | Kiểm kê mọi consumer, chuyển sang key/JWKS mới và xác nhận trước disable legacy/revoke JWT; thực hiện thủ công bởi chủ project. | DevOps/IT Security + chủ project | Danh sách consumer và kết quả kiểm tra không chứa secret; bằng chứng sau chuyển đổi/disable/login. Không tự tắt key. |
| B3 — Backup/restore/DR và vận hành (DEP-08) | Backup DB và Storage, retention backup, mã hóa, restore cô lập, RPO/RTO, DR drill, monitoring/alerting, branch protection. | DevOps/DBA/Security | Chính sách, owner, cấu hình và kết quả restore/drill/alert đã phê duyệt. Không suy có backup hay restore đạt từ trạng thái hệ thống. |
| B4 — Retention/Privacy/Legal (DEP-02/05) | Chính sách retention 12 tháng và phạm vi đã tuyển/hold; quy trình xử lý feedback chung và kiểm kê share trước guard; xử lý dữ liệu thật và egress provider. | HR Lead + Privacy/Legal + Security | Văn bản/phạm vi xử lý và phê duyệt phù hợp; đối soát các loại dữ liệu bị thiếu trong E2E-13 khi E2E được mở lại; A1–A3 không thay thế chính sách hoặc chứng cứ kỹ thuật này. |
| B5 — Dữ liệu và đánh giá pilot (DEP-06/07 và quality Phase 1) | Nguồn dữ liệu được phép, tiêu chí/nhãn HR-HM, holdout, phân xử, metric theo nhóm và báo cáo; BGE endpoint/golden set; LTR artifact và SHADOW. | HR/HM + Privacy + kỹ thuật | Phê duyệt dùng dữ liệu, dataset/labeling, metric và kết quả; không dùng synthetic smoke để khẳng định chất lượng model. BGE control đã được ghi nhận ON tại project test trong lần kiểm tra trước, LTR OFF; không suy runtime đang dùng hay gate đã đạt. Không bật production khi chưa đạt các gate. |
| B6 — Bằng chứng E2E/usability và thời gian | E2E-02–04, phần còn thiếu E2E-13; E2E-14–16/UX/Langfuse chỉ khi thuộc phạm vi được duyệt; đối chiếu các mốc thời gian trước ký. | Điều phối + DevOps + HR/HM | Quyết định mở lại E2E, preflight và từng kết quả có bằng chứng; giữ E2E-13 partial nếu thiếu coverage. Không lặp các thao tác destructive đã chạy. |
| B7 — Rà soát thuật ngữ và trải nghiệm VI/EN | **TẠM TREO — CHỜ REPORT** theo yêu cầu người dùng. HR/HM rà thuật ngữ và nhãn trong ngữ cảnh nghiệp vụ, nhất là `UNCLEAR`, điểm một phần và độ phủ; khi mở lại mới làm usability review trong phạm vi được duyệt. | HR/HM + PO + UX | Báo cáo phát hiện, ví dụ/ảnh đã loại dữ liệu nhạy cảm, mức độ/ưu tiên, đề xuất sửa và quyết định của PO; chưa có report hay nghiệm thu, không chạy E2E/dùng dữ liệu thật khi chưa được phép. |

Một số kiểm soát cũng có thể là tiền điều kiện cho môi trường thử nghiệm có rủi ro, không chỉ production. Tạm treo không có nghĩa các kiểm soát đã đạt hoặc được phép bỏ qua khi triển khai.

## 3. Điểm gọi lại và cách xử lý

1. Khi người dùng yêu cầu chuẩn bị triển khai/vận hành, mở lại báo cáo này và checklist `PHASE1_OPERATIONS_DECISION_CHECKLIST.md`; xác định môi trường và phạm vi trước.
2. Chỉ định người thực hiện, kiểm tra từng mục thực tế, ghi bằng chứng không chứa mật khẩu/token/key/CV thật; các DEP chỉ đóng khi đạt điều kiện riêng.
3. Chốt riêng việc deploy, xác minh migration tại môi trường đích, E2E và bất kỳ thao tác có ảnh hưởng dữ liệu. Không suy rằng A1–A6 cho phép chạy chúng ngay.
4. Mapping theo dõi đã thống nhất: F1.09 shortlist/dashboard, F1.13 pilot evaluation; giữ nguyên các audit lịch sử. Không suy pilot đã đạt.
5. Phase 1 vẫn chưa đóng đầy đủ; DEP-01 chỉ `CLOSED_SCOPED`, DEP-02 vẫn partial. Không bật BGE/LTR production, SSO, F2.07 automation hoặc rediscovery theo báo cáo này.
