# TÀI LIỆU KIẾN TRÚC HỆ THỐNG & SƠ ĐỒ LUỒNG DỮ LIỆU — PHASE 1 (MVP PILOT)

> **Cập nhật migration 00019:** Các hướng dẫn bật/tắt bằng biến môi trường trong tài liệu lịch sử bên dưới không áp dụng cho worker mới. Xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) về database control, giới hạn OFF và rollout/rollback không mixed-version. Code `5f5c529` đã deploy VPS test theo log người dùng; chưa chứng minh production readiness.

> **Lưu ý triển khai (05/11/2026):** Tài liệu này mô tả yêu cầu/thiết kế mục tiêu, không phải xác nhận các chức năng đã nghiệm thu. Trạng thái mã, giới hạn privacy/recovery và trạng thái migration trên project Supabase kết nối được theo dõi tại [PHASE1_GAP_ANALYSIS.md](../audit/PHASE1_GAP_ANALYSIS.md) và [DEPLOYMENT.md](../DEPLOYMENT.md).
## Dự án: VinUni AI-Native CV Matching & Ranking (HRA)

| Thuộc tính | Giá trị chuẩn hóa |
|---|---|
| **Tên tài liệu** | Kiến trúc Hệ thống, Quy trình Xử lý & Luồng Dữ liệu Phase 1 (Phase 1 Architecture, Pipeline & Data Flow Specification) |
| **Phiên bản** | 1.0 — Official Baseline Release |
| **Trạng thái** | Thiết kế Kiến trúc Kỹ thuật Chuẩn hóa (Architecture Specification) |
| **Căn cứ xây dựng** | [HRA_PRD.md], [HRA_ArchitectureDesign.md]
| **Phạm vi kỹ thuật** | Phase 1 (MVP Pilot): Thử nghiệm trên nhóm vị trí IT, CV tiếng Anh, xử lý PDF/DOCX, mô hình AI cục bộ 

---

## 1. Sơ đồ Kiến trúc Hệ thống Phase 1 (System Architecture Diagram)

Sơ đồ thể hiện 4 phân vùng logic (Zones), các thành phần từ `C-01` đến `C-11`, cùng ranh giới kiểm soát dữ liệu: **AI chỉ đóng vai trò tư vấn có dẫn chứng, quyền quyết định trạng thái tuyển dụng thuộc về con người (HR Recruiter)**.

```mermaid
flowchart TB
    %% ========================================================
    %% 1. USER ACCESS ZONE
    %% ========================================================
    subgraph ZONE_USER ["1. User Access Zone (Giao diện & Xác thực)"]
        direction LR
        HR_REC["HR Recruiter<br/>(Người dùng chính / Ra quyết định)"]
        HM["Hiring Manager<br/>(Duyệt tiêu chí & Xem Shortlist)"]
        HR_LEAD["HR Lead / Admin<br/>(Giám sát Pilot & Quản trị quyền)"]
        
        UI["C-01: Experience & Review Workspace<br/>• Giao diện song ngữ Việt - Anh (Mặc định Tiếng Việt)<br/>• Màn hình duyệt tiêu chí, danh sách ưu tiên & chi tiết CV<br/>• Dashboard theo dõi tiến độ & số liệu Pilot"]
        
        AUTH["C-02: Identity & Position Authorization<br/>• Đăng nhập nội bộ (Email & Mật khẩu)<br/>• Phân quyền RBAC theo vai trò & phạm vi Requisition ID"]
        
        HR_REC --> UI
        HM --> UI
        HR_LEAD --> UI
        UI <--> AUTH
    end

    %% ========================================================
    %% 2. CORE BUSINESS ZONE
    %% ========================================================
    subgraph ZONE_CORE ["2. Core Business Management Zone (Miền Nghiệp vụ Tuyển dụng)"]
        direction TB
        C03["C-03: Position & Criteria Governance<br/>• Quản lý Requisition & JD tiếng Anh<br/>• Tiêu chí Bắt buộc (70%) / Ưu tiên (30%)<br/>• Cơ chế Dual Approval (HR + HM) & Lưu phiên bản"]
        
        C04["C-04: Application Lifecycle<br/>• Quản lý hồ sơ ứng tuyển theo Vị trí<br/>• Quản lý trạng thái: Mới, Đang xem, Shortlist, Bị loại...<br/>• HR là chủ thể duy nhất chuyển trạng thái"]
        
        C05["C-05: CV Intake & Document Processing<br/>• Batch Upload (≤ 50 file, ≤ 10MB/file, ≤ 250MB/batch)<br/>• Bộ kiểm tra file & Hàng đợi ngoại lệ 'Cần HR kiểm tra'<br/>• Bóc tách PDF văn bản, OCR PDF scan, Text DOCX"]
        
        C09["C-09: Human Review & Collaboration<br/>• Chia sẻ Shortlist cho Hiring Manager<br/>• Ghi chú nội bộ HR riêng biệt (Bảo mật)<br/>• Tiếp nhận phản hồi chuyên môn của HM"]
        
        C10["C-10: Reporting & Pilot Measurement<br/>• Đo baseline thời gian xử lý hồ sơ<br/>• Thống kê tỷ lệ HR điều chỉnh gợi ý của AI (Override)<br/>• Giám sát tỷ lệ lỗi file & chất lượng trích xuất"]
        
        C11["C-11: Privacy, Retention & Audit Governance<br/>• Bộ đếm vòng đời 12 tháng từ ngày đóng vị trí<br/>• Hàng đợi chờ HR phê duyệt xóa thủ công<br/>• Immutable Audit Log (Ghi vết mọi thao tác xem, sửa, xóa)"]
    end

    %% ========================================================
    %% 3. AI & EVIDENCE PROCESSING ZONE
    %% ========================================================
    subgraph ZONE_AI ["3. AI & Evidence Processing Zone (Ưu tiên Xử lý Cục bộ / Local Model)"]
        direction TB
        C07["C-07: AI Orchestration & Model Governance<br/>• Điều phối tác vụ giới hạn (Allowlist Tools)<br/>• Giới hạn Context Boundary (Không trộn CV/vị trí)<br/>• Policy Guard: Chặn dùng tuổi, giới tính, ngoại hình để đánh giá"]
        
        subgraph ENGINES ["AI Processing Engines"]
            direction LR
            PARSE_ENG["AI Parser (AIC-01/02)<br/>• Bóc tách tiêu chí nháp từ JD<br/>• Cấu trúc hóa thông tin CV"]
            
            MATCH_ENG["C-08: Matching & Ranking Engine<br/>• Đối chiếu tiêu chí 4 mức (Đáp ứng tốt/Đáp ứng/Chưa rõ/Chưa đạt)<br/>• Định vị bằng chứng trích dẫn (Trang/Đoạn CV gốc)<br/>• Ranking ưu tiên tiêu chí bắt buộc trước điểm số<br/>• Tính điểm trọng số & % Độ phủ bằng chứng<br/>• Cảnh báo trùng lặp & Phân loại bất định"]
        end
        
        C06["C-06: Evidence & AI Assessment Records<br/>• Lưu thông tin nghề nghiệp trích xuất (Extracted Profile)<br/>• Lưu dẫn chứng cụ thể (Evidence Citations)<br/>• Lưu kết quả đánh giá tư vấn (Advisory Records)<br/>• Liên kết nguồn gốc (Provenance) theo phiên bản Rubric"]
    end

    %% ========================================================
    %% 4. LOGICAL DATA STORES
    %% ========================================================
    subgraph ZONE_DATA ["4. Logical Data Stores (Các kho lưu trữ logic)"]
        direction LR
        DB_POS[("D1: Position & Criteria DB")]
        DB_APP[("D2: Application Lifecycle DB")]
        DB_DOC[("D3: CV & Document Store")]
        DB_EVID[("D4: Evidence & AI Records DB")]
        DB_AUDIT[("D5: Audit & Compliance DB")]
    end

    %% Cross-zone interactions
    UI <--> C03
    UI <--> C04
    UI <--> C05
    UI <--> C09
    UI <--> C10
    
    C03 <--> DB_POS
    C04 <--> DB_APP
    C05 <--> DB_DOC
    C06 <--> DB_EVID
    C11 <--> DB_AUDIT

    C05 -->|"Văn bản bóc tách & Trạng thái file"| C07
    C03 -->|"Rubric đã duyệt & Trọng số"| C07
    C07 <--> PARSE_ENG
    C07 <--> MATCH_ENG
    PARSE_ENG --> C06
    MATCH_ENG --> C06

    C06 -.->|"Kết quả tư vấn AI (Advisory Only)"| C09
    C06 -.->|"Dẫn chứng & Thứ tự ưu tiên rà soát"| C01
    C09 -.->|"Quyết định chính thức của HR"| C04
    C04 -.->|"Ghi nhận thay đổi trạng thái"| C11
    C03 & C05 -.->|"Ghi nhận thao tác & vòng đời"| C11
```

### Chi tiết Phân vùng Kiến trúc Phase 1:

1. **User Access Zone:**
   * `C-01` (Experience & Review Workspace): Giao diện web ứng dụng song ngữ Việt – Anh, thiết kế riêng cho HR Recruiter, Hiring Manager và HR Lead. Đảm bảo hiển thị đa tầng: Danh sách tổng quan $\rightarrow$ Đối soát bằng chứng $\rightarrow$ Xem CV gốc.
   * `C-02` (Identity & Authorization): Xác thực nội bộ qua tài khoản email/mật khẩu, phân quyền chặt chẽ theo vai trò và phạm vi Requisition ID.
2. **Core Business Zone:**
   * `C-03` (Position & Criteria): Quản lý vị trí, JD và cơ chế phê duyệt tiêu chí 2 cấp (Dual Approval: HR duyệt quy trình, Hiring Manager duyệt chuyên môn). Lưu trữ lịch sử phiên bản rubric.
   * `C-04` (Application Lifecycle): Quản lý hồ sơ ứng viên và toàn bộ chu trình trạng thái tuyển dụng. Đây là **nguồn dữ liệu chuẩn duy nhất** về kết quả tuyển dụng do con người cập nhật.
   * `C-05` (CV Intake & Processing): Tiếp nhận upload theo lô (tối đa 50 file, 250 MB), kiểm tra tính toàn vẹn và bóc tách nội dung (PDF text, OCR PDF scan, Word DOCX). Phân luồng file lỗi vào hàng đợi *"Cần HR kiểm tra"*.
   * `C-09` (Review & Collaboration): Quản lý việc chia sẻ Shortlist cho Hiring Manager và phân quyền ghi chú nội bộ 2 tầng (Ghi chú bí mật của HR vs Ghi chú trao đổi vị trí).
   * `C-10` (Reporting & Pilot Measurement): Bảng điều khiển đo lường baseline thời gian, tỷ lệ điều chỉnh của HR (Override rate) và tỷ lệ lỗi file.
   * `C-11` (Privacy, Retention & Audit): Bộ đếm thời hạn lưu trữ 12 tháng từ ngày đóng vị trí, quản lý danh sách chờ HR duyệt xóa và lưu trữ nhật ký kiểm toán bất biến (Immutable Audit Log).
3. **AI & Evidence Processing Zone:**
   * `C-07` (AI Orchestration): Điều phối các tác vụ AI có giới hạn (chỉ dùng các tool trong allowlist), kiểm soát nghiêm ngặt ngữ cảnh (Context Boundary) để không rò rỉ dữ liệu giữa các vị trí. Ưu tiên xử lý mô hình AI cục bộ (Local Model/On-premise).
   * `C-08` (Matching & Ranking Engine): Thực hiện so khớp 4 mức chuẩn mực, định vị trích dẫn bằng chứng, tính điểm trọng số, tính % độ phủ bằng chứng và xếp hạng ứng viên theo nguyên tắc: **Tiêu chí bắt buộc xét trước, điểm số xét sau**.
   * `C-06` (Evidence & Records): Quản lý các bản ghi đánh giá tư vấn (Advisory Records), lưu vết provenance gắn liền với phiên bản JD và rubric cụ thể.

---

## 2. Sơ đồ Pipeline Xử lý CV & Đánh giá AI (Processing Pipeline Diagram)

Pipeline mô tả tuần tự 10 bước xử lý một lô CV từ khi HR tải lên, qua bóc tách văn bản, OCR, kiểm tra trùng, đối chiếu tiêu chí có dẫn chứng, tính độ phủ, xếp hạng ưu tiên và kết thúc bằng quyết định của con người.

```mermaid
flowchart TD
    START(["Bắt đầu: HR tải lên lô CV theo vị trí (Requisition ID)"]) --> S1

    subgraph P_STAGE1 ["Giai đoạn 1: Tiếp nhận & Kiểm tra Kỹ thuật (File Intake)"]
        S1["1. Kiểm tra Giới hạn & Định dạng (C-05 / T-UTL-01)<br/>• Kiểm tra Batch: ≤ 50 file, ≤ 10MB/file, tổng ≤ 250MB<br/>• Kiểm tra định dạng hỗ trợ: PDF, DOCX (tiếng Anh)"]
        S1 --> CHK_READABLE{"File có đọc được không?<br/>(Không khóa password, không hỏng, không quá mờ?)"}
        
        CHK_READABLE -- "Không đọc được" --> ERR_QUEUE["Hàng đợi ngoại lệ: Gắn nhãn 'Cần HR kiểm tra'<br/>(Không gán điểm 0, không tự động loại ứng viên)"]
        ERR_QUEUE --> HR_MANUAL["HR rà soát file thủ công / Yêu cầu bổ sung"]
        HR_MANUAL --> S3
        
        CHK_READABLE -- "Hợp lệ" --> S2["2. Bóc tách Văn bản & OCR (C-05 / T-UTL-02, 03)<br/>• PDF có text: Trích xuất chuỗi văn bản trực tiếp<br/>• PDF scan: Chạy OCR nhận dạng chữ bản quét<br/>• DOCX: Trích xuất văn bản thông thường"]
    end

    subgraph P_STAGE2 ["Giai đoạn 2: Cấu trúc hóa & Kiểm tra Trùng lặp"]
        S2 --> S3["3. Cấu trúc hóa Thông tin Nghề nghiệp (AIC-02 / T-GEN-02)<br/>• Trích xuất có cấu trúc: Học vấn, Kinh nghiệm, Kỹ năng, Chứng chỉ<br/>• Cho phép HR chỉnh sửa trực tiếp các thông tin trích xuất sai"]
        
        S3 --> S4["4. Nhận diện Trùng lặp trong cùng Vị trí (AIC-06 / T-REC-04)<br/>• Đối khớp: Email, Số điện thoại, Độ tương đồng nội dung<br/>• Nếu nghi ngờ trùng: Gắn cờ cảnh báo (HR tự quyết định, không tự gộp/xóa)"]
    end

    subgraph P_STAGE3 ["Giai đoạn 3: Đối chiếu Bằng chứng & Đánh giá Tiêu chí"]
        S4 --> S5["5. Nạp Ngữ cảnh Tiêu chí đã Duyệt (C-03 / T-CRM-02)<br/>• Nạp Rubric phiên bản đã duyệt của Vị trí<br/>• Tách nhóm: Bắt buộc (70%) và Ưu tiên (30%)<br/>• Loại trừ dữ liệu nhạy cảm (tuổi, giới tính, ngoại hình)"]
        
        S5 --> S6["6. Đối chiếu Bằng chứng từng Tiêu chí (AIC-03 / T-REC-01)<br/>• Đánh giá 4 mức: Đáp ứng tốt / Đáp ứng / Chưa rõ / Chưa đáp ứng<br/>• Định vị bằng chứng: Trích dẫn đoạn văn & số trang CV gốc<br/>• 'Chưa rõ / Chưa tìm thấy bằng chứng' KHÔNG đồng nghĩa 'Chưa đáp ứng'"]
    end

    subgraph P_STAGE4 ["Giai đoạn 4: Tính toán Chỉ số & Xếp hạng Ưu tiên"]
        S6 --> S7["7. Tính Điểm & Độ phủ Bằng chứng (C-08 / T-UTL-05)<br/>• Điểm Matching = Tổng trọng số các tiêu chí đạt yêu cầu<br/>• Tính % Độ phủ bằng chứng (Evidence Coverage)"]
        
        S7 --> CHK_COV{"Độ phủ bằng chứng<br/>≥ 70%?"}
        CHK_COV -- "Dưới 70%" --> FLAG_LOW_COV["Gắn cờ: 'Chưa đủ dữ liệu để xếp hạng ổn định'<br/>(Chuyển nhóm Cần HR xác minh)"]
        CHK_COV -- "Đạt ≥ 70%" --> S8
        FLAG_LOW_COV --> S8
        
        S8["8. Phân nhóm & Xếp hạng trong cùng Vị trí (AIC-04 / T-REC-02)<br/>• Ưu tiên 1: Mức độ đáp ứng tiêu chí Bắt buộc (Must-have)<br/>• Ưu tiên 2: Điểm số trọng số tổng hợp (Score)<br/>• Phân nhóm rà soát: Đạt tiêu chí bắt buộc / Cần xác minh / Dấu hiệu miss-match"]
    end

    subgraph P_STAGE5 ["Giai đoạn 5: Lưu trữ Tư vấn & Ra Quyết định"]
        S8 --> S9["9. Lưu Bản đánh giá Tư vấn AI (C-06 / T-CRM-04)<br/>• Lưu kết quả tư vấn (Advisory Record) kèm Provenance & Rubric Version<br/>• Ghi nhận sự kiện vào Audit Log (C-11)"]
        
        S9 --> S10["10. Thẩm định & Ra Quyết định Tuyển dụng (C-01, C-04, C-09)<br/>• HR kiểm tra danh sách ưu tiên, nhấp xem trích dẫn & đối chiếu CV gốc<br/>• HR cập nhật trạng thái: Shortlist / Đang xem / Bị loại ở vòng sàng lọc<br/>• Chia sẻ Shortlist cho Hiring Manager xem & phản hồi nhận xét"]
    end

    S10 --> END(["Hoàn tất vòng sàng lọc CV"])
```

### Các Chốt chặn Kiểm soát Chất lượng trong Pipeline:
* **Chốt chặn 1 (File không đọc được):** Không loại bỏ ứng viên; tự động đẩy vào hàng đợi kiểm tra thủ công.
* **Chốt chặn 2 (Chưa rõ thông tin):** Phân biệt rạch ròi giữa "Chưa rõ" (thiếu thông tin) và "Chưa đáp ứng" (thông tin mâu thuẫn yêu cầu).
* **Chốt chặn 3 (Độ phủ bằng chứng < 70%):** Gắn cờ cảnh báo không ổn định để HR kiểm tra kỹ lưỡng, tránh ngộ nhận điểm cao giả tạo.
* **Chốt chặn 4 (Quyết định tuyển dụng):** AI không bao giờ tự động chuyển trạng thái hồ sơ sang "Bị loại" hoặc "Shortlist".

---

## 3. Sơ đồ Luồng Dữ liệu (Data Flow Diagram - DFD Level 1)

Sơ đồ thể hiện tường minh các thực thể bên ngoài (External Entities), các tiến trình xử lý (Processes), các kho dữ liệu logic (Data Stores) và các luồng thông tin chạy qua các ranh giới tin cậy (Trust Boundaries).

```mermaid
flowchart LR
    %% ========================================================
    %% ACTORS / EXTERNAL ENTITIES
    %% ========================================================
    subgraph ACTORS ["Tác nhân bên ngoài (Actors)"]
        HR["HR Recruiter"]
        HM["Hiring Manager"]
        APPL["Ứng viên (Hồ sơ CV)"]
    end

    %% ========================================================
    %% DATA STORES
    %% ========================================================
    subgraph STORES ["Kho dữ liệu logic (Logical Data Stores)"]
        D1[("D1: Vị trí & Tiêu chí đã Duyệt<br/>(JD tiếng Anh, Rubric, Trọng số, Version)")]
        D2[("D2: Tệp CV & Trạng thái File<br/>(File PDF/DOCX gốc, File Processing Status)")]
        D3[("D3: Thông tin Trích xuất & Dẫn chứng<br/>(Structured Profile, Evidence Text, Page Ref)")]
        D4[("D4: Bản đánh giá Tư vấn AI<br/>(4 Mức tiêu chí, Điểm số, % Coverage, Ranking)")]
        D5[("D5: Trạng thái Tuyển dụng Ứng viên<br/>(Application Lifecycle Status, Lý do loại)")]
        D6[("D6: Nhật ký Kiểm toán & Tuân thủ<br/>(Audit Logs, Lịch Retention 12 tháng)")]
    end

    %% ========================================================
    %% PROCESSES
    %% ========================================================
    subgraph PROCESSES ["Các Tiến trình Xử lý (Processes)"]
        P1["P1: Quản trị Vị trí & Phê duyệt Tiêu chí<br/>(C-03: Criteria Dual Approval)"]
        P2["P2: Tiếp nhận & Xử lý Tệp CV<br/>(C-05: Intake, Validate, OCR)"]
        P3["P3: Cấu trúc hóa & Trích xuất Dẫn chứng<br/>(C-06, C-07: Profile & Evidence Extraction)"]
        P4["P4: Đối chiếu Tiêu chí & Xếp hạng AI<br/>(C-07, C-08: Matching & Ranking Engine)"]
        P5["P5: Thẩm định Bằng chứng & Ra Quyết định<br/>(C-01, C-04, C-09: Human Review & Transition)"]
        P6["P6: Quản trị Lưu trữ & Kiểm toán Dữ liệu<br/>(C-11: Retention 12M & Purge Workflow)"]
    end

    %% ========================================================
    %% DATA FLOWS
    %% ========================================================
    %% Flow 1: Criteria setup
    HM -->|"1. Đề xuất nhu cầu & Duyệt chuyên môn"| P1
    HR -->|"2. Rà soát tính rõ ràng & Duyệt rubric vị trí"| P1
    P1 -->|"Ghi nhận JD & Bộ tiêu chí đã duyệt (v1.0)"| D1

    %% Flow 2: CV Intake
    APPL -.->|"3. Nộp CV tiếng Anh (PDF/DOCX)"| HR
    HR -->|"4. Upload lô CV theo Vị trí"| P2
    P2 -->|"Lưu file gốc & trạng thái đọc/OCR"| D2
    P2 -->|"5. Chuỗi văn bản sạch & metadata"| P3

    %% Flow 3: Parsing & Evidence
    P3 -->|"Lưu hồ sơ cấu trúc & vị trí trích dẫn"| D3
    D3 -->|"6. Cung cấp thông tin nghề nghiệp & bằng chứng"| P4
    D1 -->|"7. Cung cấp Rubric đã duyệt & trọng số"| P4

    %% Flow 4: Matching & Advisory Records
    P4 -->|"8. Ghi nhận kết quả tư vấn AI & xếp hạng"| D4
    
    %% Flow 5: Human Decision
    D4 -->|"9. Hiển thị danh sách ưu tiên & bằng chứng"| P5
    D2 -.->|"Đối chiếu CV gốc khi cần kiểm chứng"| P5
    HR -->|"10. Thẩm định bằng chứng & Cập nhật trạng thái"| P5
    P5 -->|"Chia sẻ Shortlist ứng viên"| HM
    HM -->|"Gửi nhận xét chuyên môn"| P5
    P5 -->|"11. Ghi nhận trạng thái tuyển dụng chính thức"| D5

    %% Flow 6: Audit & Retention
    P1 & P2 & P4 & P5 -->|"Ghi nhật ký thao tác (Audit events)"| D6
    D5 -->|"12. Sự kiện đóng vị trí tuyển dụng"| P6
    P6 -->|"Đếm 12 tháng & thông báo danh sách đến hạn"| D6
    HR -->|"13. Phê duyệt xác nhận xóa hồ sơ"| P6
    P6 -->|"Xóa vĩnh viễn dữ liệu ứng tuyển đến hạn"| D2 & D3 & D4 & D5
```

---

## 4. Tóm tắt các Nguyên tắc Kiến trúc Cốt lõi của Phase 1

| Nguyên tắc | Cơ chế kiểm soát kiến trúc |
|---|---|
| **Human-in-control (Con người quyết định)** | Toàn bộ kết quả từ AI Engine (`C-08`) chỉ được ghi vào kho tư vấn `D4 (Advisory Records)`. Trạng thái tuyển dụng chính thức tại `D5` **chỉ do HR Recruiter cập nhật** qua `P5`. |
| **Bằng chứng trước điểm số** | Mọi nhận định đánh giá bắt buộc phải có liên kết dẫn chứng `D3` (số trang, đoạn văn trong CV gốc). Không có điểm số độc lập thiếu căn cứ. |
| **Tách biệt 3 miền trạng thái** | 1. **Trạng thái file (`D2`):** Đọc thành công / Lỗi đọc / Cần HR kiểm tra.<br/>2. **Nhóm matching (`D4`):** Đạt bắt buộc / Cần xác minh / Dấu hiệu miss-match.<br/>3. **Trạng thái tuyển dụng (`D5`):** Mới / Đang xem / Shortlist / Bị loại ở vòng sàng lọc... |
| **Xử lý thiếu thông tin** | Trường hợp CV không có thông tin hoặc OCR mờ được gắn nhãn **"Chưa rõ"**, đưa vào hàng đợi xác minh; **tuyệt đối không quy đổi thành "Chưa đáp ứng"** hay chấm điểm 0. |
| **Bảo vệ dữ liệu & Xử lý cục bộ** | Ưu tiên triển khai mô hình AI trên hạ tầng cục bộ (On-premise/Private environment) của VinUni. Loại trừ hoàn toàn dữ liệu nhân khẩu học nhạy cảm (tuổi, giới tính, ảnh chân dung) khỏi context đánh giá. |
| **Vòng đời dữ liệu (Retention 12 tháng)** | Đếm 12 tháng kể từ ngày Requisition chuyển sang trạng thái "Đóng". Việc xóa dữ liệu vật lý phải có **xác nhận chủ động của HR có thẩm quyền**; không tự động xóa ngầm. |

---

## 5. Ma trận Ánh xạ Thành phần Kiến trúc & Yêu cầu Nghiệp vụ (Traceability Matrix)

| Yêu cầu PRD Phase 1 | Thành phần Kiến trúc | Công cụ Logic (Tools) | Kho Dữ liệu | Cơ chế Kiểm soát & Tiêu chí Chấp thuận |
|---|---|---|:---:|---|
| **F1.01: Quản lý Vị trí & JD** | `C-03` Governance | `T-CRM-01` | `D1` | Phân quyền Requisition; JD tiếng Anh; Trạng thái Open/Paused/Closed. |
| **F1.02: Trích xuất & Duyệt Tiêu chí** | `C-03`, `C-07` | `T-GEN-01`, `T-CRM-02` | `D1` | AI gợi ý chỉ là bản nháp; Bắt buộc 70% / Ưu tiên 30%; Dual Approval HR & HM. |
| **F1.03: Tiếp nhận CV theo Batch** | `C-05` Intake | `T-UTL-01` | `D2` | Kiểm tra giới hạn: ≤ 50 file, ≤ 10MB/file, ≤ 250MB/batch; PDF/DOCX. |
| **F1.04: Bóc tách & OCR CV** | `C-05` Processing | `T-UTL-02`, `T-UTL-03` | `D2`, `D3` | PDF text bóc trực tiếp; PDF scan chạy OCR; file mờ/hỏng vào hàng đợi thủ công. |
| **F1.05: Matching có Bằng chứng** | `C-08` Engine | `T-REC-01`, `T-UTL-04` | `D4` | 4 Mức đánh giá chuẩn; dẫn chứng trích đoạn & số trang; Chưa rõ $\ne$ Không đạt. |
| **F1.06: Ranking Minh bạch** | `C-08` Engine | `T-REC-02`, `T-UTL-05` | `D4` | Xét tiêu chí bắt buộc trước; cảnh báo độ phủ < 70%; chỉ so sánh cùng vị trí. |
| **F1.07: Xử lý Ngoại lệ & Trùng lặp** | `C-05`, `C-08` | `T-REC-03`, `T-REC-04` | `D2`, `D4` | Cảnh báo trùng cùng vị trí (Fuzzy match); không tự động gộp/xóa. |
| **F1.08: Quản trị Quyết định Tuyển dụng** | `C-04` Lifecycle | `C-01` UI | `D5` | HR là người duy nhất chuyển trạng thái; AI không có quyền cập nhật `D5`. |
| **F1.09: Shortlist & Dashboard** | `C-01`, `C-09` | `T-CRM-04` | `D4`, `D5` | HM chỉ xem vị trí phụ trách; ghi chú nội bộ HR được bảo vệ nghiêm ngặt. |
| **F1.10: Phân quyền & Retention 12T** | `C-02`, `C-11` | `T-KNO-01` | `D6` | RBAC chặt chẽ; đếm 12 tháng từ ngày đóng; HR xác nhận xóa từng hồ sơ. |
| **F1.11: Ưu tiên Xử lý Cục bộ** | `C-07` Model Gov | `T-UTL-06` | - | Mô hình chạy on-premise; không gửi dữ liệu CV production ra cloud công cộng. |
| **F1.12: Giao diện Song ngữ** | `C-01` Workspace | `C-01` UI | - | Chuyển đổi song ngữ Việt - Anh linh hoạt, mặc định tiếng Việt. |
| **F1.13: Đánh giá Nghiệm thu Pilot** | `C-10` Reporting | `C-10` Metrics | `D6` | Kiểm thử trên 200–300 mẫu chuẩn IT (Macro-F1 $\ge 0.80$, False Negatives $\le 5\%$). |

---

## 6. Cập nhật triển khai sau baseline Phase 1 (07/11/2026)

Tài liệu trên là baseline thiết kế Phase 1. Phần hiện thực hiện tại bổ sung hai lớp tùy chọn trong cùng `C-08 Matching & Ranking Engine`, không tạo service riêng và không thay đổi ranh giới quyết định của HR:

| Lớp bổ sung | Vị trí kiến trúc | Trạng thái/gate |
|---|---|---|
| **Semantic retrieval (pgvector/BGE)** | `C-07` điều phối embedding provider; `C-06` lưu vector phái sinh; `C-08` merge lexical + semantic candidate chunks trước LLM fallback. | Tắt mặc định (`SEMANTIC_RETRIEVAL_ENABLED=false`). Khi bật, chỉ bổ sung tối đa 5 candidate chunks/criterion; similarity không tạo finding và quote vẫn phải verify. |
| **Learning-to-Rank (LTR)** | `C-08` tính `ltr_score` sau deterministic score/coverage; registry artifact thuộc dữ liệu vận hành/model governance. | Mặc định `OFF`. `SHADOW` không đổi thứ hạng; `ACTIVE` chỉ reorder trong cùng mandatory status/coverage gate khi artifact đạt holdout gate và được phê duyệt. |

Trong sơ đồ pipeline, semantic retrieval nằm giữa bước đối chiếu rule và LLM fallback cho criterion chưa quyết định; LTR nằm sau bước tính score/coverage và trước khi lưu ranking snapshot. Dữ liệu vector không dùng để tìm kiếm xuyên vị trí và không triển khai Talent Pool/Candidate Rediscovery trong cập nhật này.

Chi tiết cấu hình, fingerprint, migration và điều kiện kích hoạt: [MATCHING_STABILITY.md](MATCHING_STABILITY.md), [HRA_DatabaseDesign.md](HRA_DatabaseDesign.md), [DEPLOYMENT.md](../DEPLOYMENT.md).

