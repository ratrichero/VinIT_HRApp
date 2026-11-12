# Triển khai VinUni HRApp trên VPS Ubuntu

> **Cập nhật migration 00019:** Các hướng dẫn bật/tắt bằng biến môi trường trong tài liệu lịch sử bên dưới không áp dụng cho worker mới. Xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) về database control, giới hạn OFF và rollout/rollback không mixed-version. Chưa triển khai thay đổi này lên môi trường thật.

> Hướng dẫn này dành cho **staging/pilot với dữ liệu tổng hợp**, chưa phải chứng nhận production. Docker/Compose, Supabase Auth/Storage thật, OCR và model thật chưa được kiểm thử đầu-cuối trong môi trường đích. Không dùng CV thật trước khi hoàn tất kiểm thử, phê duyệt bảo mật/pháp lý, retention, bảo vệ session/XSS, backup/restore và đánh giá AI. Không đưa secret vào Git, log, ticket hay chat.

## 1. Kiến trúc và điều kiện

```text
Trình duyệt -- HTTPS :443 --> Nginx trên VPS --> 127.0.0.1:3000 frontend
                                              --> /v1 proxy nội bộ --> backend:8000
Backend + worker --> PostgreSQL/Supabase Auth + Storage; model được phê duyệt
```

Ví dụ dùng Ubuntu 24.04 LTS, DNS `hr.example.com` đã trỏ đến IP VPS, SSH quản trị và quyền `sudo`, Docker Engine 28+ với Compose plugin hiện hành, Nginx và Certbot. Mở cổng 80/443 và cổng SSH thực tế ở firewall nhà cung cấp/OS; nếu có bản ghi AAAA, IPv6 cũng phải hoạt động. Ước lượng ban đầu cho app/OCR thử nghiệm: 2 vCPU, 4 GB RAM và 30 GB ổ đĩa, sau đó đo tải; model local thường cần RAM/VRAM riêng lớn hơn nhiều. Upload tối đa 250 MB/lô có thể tăng bộ nhớ/đĩa tạm. Giới hạn truy cập staging bằng VPN/IP allowlist; không coi HTTPS là đủ bảo mật.

- Supabase/PostgreSQL, Auth, hai bucket private `cv-originals`/`cv-extracted-text` và model **phải được chuẩn bị riêng**. Compose không tạo các dịch vụ đó. Backend xác minh JWT theo thuật toán ký: token asymmetric/JWKS (ví dụ ES256) qua `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, token HS256 legacy bằng `SUPABASE_JWT_SECRET`; cả hai đều kiểm tra audience `authenticated`.
- Cần tài khoản Auth và profile/role tương ứng; ở snapshot trước 00004, project kết nối chưa có auth user/profile/ADMIN (không khẳng định trạng thái hiện tại). HR và HM phải là hai người/tài khoản khác nhau cho hai bước duyệt. Tài khoản mới tạo từ app phải đổi mật khẩu tạm trước khi truy cập nghiệp vụ.
- Dùng PostgreSQL direct connection qua TLS; chỉ dùng session pooler sau khi xác minh session/backend PID và advisory lock được giữ xuyên các transaction. **Không dùng transaction/statement pooling** cho worker. Direct Supabase có thể cần IPv6; xác minh tuyến mạng hoặc session pooler phù hợp với project.
- `00004`–`00010` đã được áp vào project `myrymlqdbyqmpynesiwk`, gồm `20261107021622 structured_requirement_specs` và `20261107022845 pgvector_bge_ltr` ngày 07/11/2026. Backend hiện tại yêu cầu 00005–00010; với project/môi trường khác, đối chiếu [lịch sử và checklist migration](../DEPLOYMENT.md#lịch-sử-project-đã-kết-nối), xin phê duyệt riêng, thử staging/backup/restore và drain worker cũ. Tên/version remote là timestamp, khác tiền tố file local; **không chạy `supabase db push`, reset hoặc migration repair mù quáng**.
- Service-role key legacy từng lộ trong lịch sử Git **vẫn đang bật** trên project `myrymlqdbyqmpynesiwk` (05/11/2026 kiểm tra `list_api_keys` còn `anon`+`service_role` JWT, đồng thời đã có `sb_publishable_z2Ynu`/`sb_secret_rLbWw`). Thu hồi trọn vẹn cần: chuyển mọi client/backend/worker sang `sb_publishable_`/`sb_secret_`, deactivate legacy (Dashboard **Settings → API Keys → Legacy** hoặc `PUT /v1/projects/{ref}/api-keys/legacy?enabled=false`), và revoke legacy JWT secret sau khi mọi backend đã chạy bản hỗ trợ JWKS/asymmetric; nếu còn backend bản cũ chỉ verify `HS256`, việc revoke/đổi signing key sẽ làm bản cũ không đăng nhập được. Connector hiện không có thao tác deactivate legacy, phải làm thủ công và kiểm chứng. Browser không được nhận service-role key hay DB URL.

## 2. Cài phần mềm trên VPS

Đây là ví dụ cho bản Ubuntu được Docker hỗ trợ; kiểm tra [tài liệu Docker Engine chính thức](https://docs.docker.com/engine/install/ubuntu/) và chính sách máy chủ trước khi chạy. Không pipe script cài đặt bên ngoài trực tiếp vào shell.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git nginx certbot python3-certbot-nginx
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
  "$(dpkg --print-architecture)" "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker nginx
sudo docker version
sudo docker compose version
```

Lệnh trong tài liệu dùng `sudo docker` thay vì thêm người dùng vào nhóm `docker`: quyền Docker tương đương quyền root. Kiểm tra firewall nhà cung cấp và UFW/IPv6 theo chính sách; nếu bật UFW qua SSH, cho phép **cổng SSH đang dùng trước** để tránh tự khóa. Không dựa riêng vào UFW để chặn port Docker: chỉ bind app vào loopback và kiểm tra thêm từ một máy bên ngoài.

## 3. Lấy mã theo commit được duyệt

Dùng quyền đọc repository hợp lệ trên VPS, ví dụ SSH deploy key chỉ đọc được quản lý riêng; không đưa token vào URL hoặc shell history. Thay hai giá trị dưới đây bằng thông tin thực tế. Luôn pin SHA đã review; không deploy tự động từ đầu nhánh đang thay đổi.

```bash
REPO_URL='git@github.com:ratrichero/VinIT_HRApp.git'
RELEASE_SHA='THAY_BANG_COMMIT_SHA_DA_DUYET'
sudo install -d -o "$USER" -g "$(id -gn)" -m 0750 /opt/vinit-hrapp
git clone "$REPO_URL" /opt/vinit-hrapp
cd /opt/vinit-hrapp
git fetch origin
git checkout --detach "$RELEASE_SHA"
git rev-parse HEAD
```

## 4. Cấu hình bí mật, TLS database và AI

Lấy CA PostgreSQL của project qua kênh nhà cung cấp đã xác thực, xác minh fingerprint theo quy trình tổ chức rồi đặt nó trên VPS. CA không phải mật khẩu, nhưng không được thay bằng file chưa tin cậy. Thay đường dẫn nguồn ví dụ:

```bash
sudo install -d -m 0755 /etc/vinit-hrapp
sudo install -m 0644 /secure/path/supabase-db-ca.crt /etc/vinit-hrapp/supabase-db-ca.crt
cd /opt/vinit-hrapp
umask 077
cp .env.example .env
chmod 600 .env
${EDITOR:-nano} .env
```

Điền các giá trị thật **trong editor/secret manager**, không paste vào lệnh hay commit. Ví dụ hình dạng (không phải credential hoặc endpoint hoạt động):

```dotenv
APP_ENV=production
DEBUG=false
HRA_BACKEND_BIND=127.0.0.1
HRA_FRONTEND_BIND=127.0.0.1
HRA_DB_CA_PATH=/etc/vinit-hrapp/supabase-db-ca.crt
DATABASE_URL=postgresql://DB_USER:URL_ENCODED_PASSWORD@DB_HOST:5432/postgres?sslmode=verify-full&sslrootcert=/run/secrets/supabase-db-ca.crt
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=THAY_BANG_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=THAY_BANG_SERVICE_ROLE_KEY_DA_ROTATE
# Chỉ cần khi còn chấp nhận token HS256 legacy; token ES256 được verify qua JWKS.
SUPABASE_JWT_SECRET=
# Để trống; chỉ cấu hình tạm trong thời gian bootstrap được phê duyệt.
ADMIN_BOOTSTRAP_TOKEN=
STORAGE_BACKEND=supabase
SUPABASE_STORAGE_BUCKET_CV=cv-originals
SUPABASE_STORAGE_BUCKET_EXTRACTED=cv-extracted-text
LLM_PROVIDER=local
LLM_PROVIDER_NAME=
LLM_MODEL_NAME=llama3.1:8b
LLM_API_BASE=http://10.20.0.12:11434/v1
LLM_API_KEY=
AI_CONFIG_ENCRYPTION_KEY=
LLM_ALLOWED_MODELS=[]
LLM_ALLOWED_API_BASES=[]
ALLOW_EXTERNAL_API=false
SEMANTIC_RETRIEVAL_ENABLED=false
EMBEDDING_PROVIDER=disabled
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_INDEX_VERSION=bge-index-v1
SEMANTIC_TOP_K=5
SEMANTIC_MIN_SIMILARITY=0.35
LTR_MODE=OFF
LTR_MODEL_PATH=
LTR_MODEL_VERSION=
LTR_MIN_NDCG_AT_10=0.70
LTR_MIN_PAIRWISE_ACCURACY=0.65
LTR_MIN_HOLDOUT_EXAMPLES=20
LTR_MIN_HOLDOUT_GROUPS=2
CORS_ORIGINS=["https://hr.example.com"]
```

- Dùng DB host/user/port thực tế và tài khoản backend được cấp quyền tối thiểu cần thiết trên `app_private`, có kết nối session ổn định. Backend kết nối SQL trực tiếp, không đặt `auth.uid()` theo từng request: role DB phải được DBA cấu hình quyền table/schema **và** khả năng truy cập phù hợp với RLS (ví dụ một role backend-only được phê duyệt có BYPASSRLS); chỉ grant table cho role thường là chưa đủ. Đây là quyền mạnh, không cấp cho browser, và phải test đầy đủ nghiệp vụ. Service-role API key không tự trở thành tài khoản đăng nhập PostgreSQL. URL-encode các ký tự đặc biệt trong password; `verify-full` kiểm tra cả CA và hostname. `docker-compose.vps.yml` mount file CA host từ `HRA_DB_CA_PATH` vào `/run/secrets/supabase-db-ca.crt` chỉ đọc và báo lỗi nếu file nguồn không tồn tại. `/health/ready` chỉ chứng minh kết nối, không chứng minh quyền RLS/CRUD; kiểm tra nghiệp vụ riêng và không hạ TLS chỉ để bỏ qua lỗi.
- `SUPABASE_ANON_KEY`, service-role key và JWT secret phải thuộc đúng project; service-role/JWT secret chỉ nằm trong môi trường backend. Để quản lý tài khoản, role DB backend còn cần quyền `SELECT` trên **hai cột `id`, `email` của `auth.users`**, và quyền phù hợp trên bảng `app_private.account_initialization`/trigger mới; DBA cấp/test theo chính sách, không cấp quyền đọc toàn bộ Auth cho browser. Đồng bộ đồng hồ Auth, DB, API: chặn token cũ dựa trên `iat` và thời gian DB. Restrict `.env`, backups và quyền Docker; environment container có thể đọc bởi quản trị viên Docker. Không chạy `docker compose config` thông thường trong log vì có thể in secret; dùng `config --quiet`.
- `10.20.0.12` chỉ minh họa một model endpoint private đã được phép; thay bằng địa chỉ **từ container backend** có thể truy cập. `127.0.0.1`/`localhost` bên trong container là chính container backend, không phải model chạy trên host. Endpoint mặc định và model mặc định tự nằm trong allowlist; các giá trị bổ sung dùng JSON array. Nếu chưa có model thì không chạy xử lý AI.
- Cấu hình AI ACTIVE đã có trong DB được ưu tiên hơn env. Sau khi có ADMIN hãy vào **Admin → Cấu hình AI** để tạo/kích hoạt version reachable từ backend; không tự sửa hàng ACTIVE qua SQL. Với `local`/`openai`/`azure`, model/endpoint vẫn theo allowlist. Riêng **OpenAI Compatible**, Admin nhập tên nhà cung cấp, Base URL, API Key và Model; API key được mã hóa bằng `AI_CONFIG_ENCRYPTION_KEY` trước khi lưu và không hiển thị lại. Thay env/secret cần restart/redeploy mọi process; job đang chạy giữ snapshot công khai cũ và nạp lại key đã ghim trong bộ nhớ khi phục hồi. `allowed_by_this_process` không chứng minh model hoạt động.
- Nếu sử dụng endpoint public, phải được phê duyệt, dùng HTTPS và đặt `ALLOW_EXTERNAL_API=true`. Che PII và guardrails hiện chỉ best effort; egress firewall, DLP, TLS, đánh giá bias và giám sát vẫn bắt buộc. Nhãn `azure` chỉ hoạt động qua gateway OpenAI-compatible/Bearer, không hỗ trợ Azure native. Xem [chính sách AI](../DEPLOYMENT.md#cấu-hình-ai-và-egress).
- Giữ semantic/LTR tắt như ví dụ trên cho tới khi có BGE endpoint thật, golden set và quy trình phê duyệt artifact LTR. Nếu bật BGE trong Docker, `EMBEDDING_API_BASE` phải là địa chỉ reachable **từ container backend**, không dùng `127.0.0.1` để trỏ tới service chạy trên host.

## 5. Khởi chạy Compose

Thực hiện từ `/opt/vinit-hrapp`; lệnh đầu chỉ kiểm cấu hình mà không in env. File base bind `3000` và `8000` vào `127.0.0.1` theo mặc định; override VPS mount CA. Dùng một replica backend ban đầu: worker chạy trong mỗi process API.

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.vps.yml config --quiet
sudo docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build
sudo docker compose -f docker-compose.yml -f docker-compose.vps.yml ps
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:3000/
ss -ltn | grep -E ':(3000|8000) '
```

Phải thấy hai cổng chỉ bind `127.0.0.1`, không phải `0.0.0.0`/`::`. Từ mạng ngoài, kiểm tra 3000/8000 không truy cập được; chỉ public Nginx 80/443. `/health/ready` chỉ kiểm tra kết nối DB, không chứng minh quyền nghiệp vụ, Auth, Storage hoặc AI. Local CV volume vẫn tồn tại dù dùng Supabase Storage; **không dùng `docker compose down -v`** với dữ liệu cần giữ. Đảm bảo backup/mã hóa cho bất kỳ volume hoặc thư mục tạm nào chứa CV.

## 6. Nginx và HTTPS

Chỉnh `server_name` dưới đây thành domain thật. Mở port 80 để cấp/gia hạn chứng chỉ; chỉ bật `listen [::]:80` sau khi IPv6 VPS hoạt động. Nginx proxy **toàn bộ** request tới frontend; browser không gọi backend/localhost trực tiếp. `260m` lớn hơn 250.000.000 byte/lô cộng multipart overhead; backend vẫn áp giới hạn riêng. Tắt buffering giảm nguy cơ ghi CV vào proxy temp file nhưng vẫn cần đánh giá cấu hình/log/ổ đĩa thực tế.

```bash
sudo tee /etc/nginx/sites-available/vinit-hrapp >/dev/null <<'NGINX'
server {
    listen 80;
    # listen [::]:80;
    server_name hr.example.com;
    client_max_body_size 260m;
    server_tokens off;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_connect_timeout 10s;
        proxy_send_timeout 480s;
        proxy_read_timeout 480s;
    }
}
NGINX
# Sửa domain trong file trước khi enable; tránh xung đột site đã có.
sudo nano /etc/nginx/sites-available/vinit-hrapp
sudo ln -s /etc/nginx/sites-available/vinit-hrapp /etc/nginx/sites-enabled/vinit-hrapp
sudo nginx -t && sudo systemctl reload nginx
# Thay domain bằng domain thực tế; Certbot sẽ yêu cầu thông tin quản trị cần thiết.
sudo certbot --nginx -d hr.example.com --redirect
sudo certbot renew --dry-run
```

Kiểm tra `https://<domain>/` từ ngoài VPS, certificate/redirect và lịch gia hạn. Cấu hình hạn chế IP/VPN, chống brute force/rate limit ở gateway và giám sát theo chính sách. Không ghi request body, mật khẩu, token hay CV vào access/error log; giới hạn quyền và retention log. Các config Nginx/certificate chưa được thử trên VPS trong phiên này.

## 7. Bootstrap người dùng và smoke test

> Các bước dưới đây áp dụng khi **00005 đã được phê duyệt và áp thành công** cho đúng môi trường. Project `myrymlqdbyqmpynesiwk` đã áp `20261105163626 account_administration` ngày 05/11/2026 16:36 UTC (marker mở vì chưa có ADMIN); các môi trường khác phải làm staging/backup riêng. Chưa kiểm thử Supabase Auth/Storage/LLM thật trên VPS trong phiên này.

1. Kiểm tra lịch sử người dùng/role và marker `app_private.account_initialization` bằng quyền DBA trước khi mở setup. Migration đánh dấu đã khởi tạo nếu có **bất kỳ** assignment ADMIN nào, kể cả đã thu hồi; trigger cũng đóng setup nếu ADMIN được cấp ngoài app. Nếu ADMIN từng bị xóa **trước** migration thì lịch sử đó có thể không còn trong bảng role: phải kiểm tra nguồn audit/backup, không mở bootstrap mù. Marker không bị reset khi tài khoản Admin bị khóa, mất role hoặc bị xóa.
2. Chỉ nếu đây là hệ thống chưa từng có ADMIN, người vận hành tạo một mã ngẫu nhiên mạnh (ít nhất 32 byte entropy, ví dụ `secrets.token_urlsafe(32)` trong secret manager), đặt vào `ADMIN_BOOTSTRAP_TOKEN` trên các backend. Không ghi mã vào Git, log, command history, ticket hay chat. Chỉ mở trang setup qua HTTPS và mạng/VPN/IP allowlist tin cậy; áp rate limit/chống brute force ở gateway. Biến để trống mặc định thì setup đóng. Kiểm tra service key và JWT/Auth của project tương thích; service key chỉ ở backend.
3. Người được ủy quyền mở trang đăng nhập → **Khởi tạo Admin đầu tiên**, nhập mã và tự đặt email, tên, mật khẩu. API dùng Supabase Admin tạo Auth identity và `email_confirm=true`, vì vậy **phải xác minh email/đúng người qua kênh độc lập** trước; không gửi password hay mã setup qua chat. Khởi tạo chỉ được chấp nhận một lần, kể cả khi có hai yêu cầu đồng thời. Đây là giới hạn cho **bootstrap**, không giới hạn tổng số ADMIN về sau.
4. Sau khi tạo thành công, xóa `ADMIN_BOOTSTRAP_TOKEN` khỏi mọi instance/secret rollout, restart và kiểm tra setup đã đóng. Nếu mất/khóa tất cả ADMIN sau này, DBA được ủy quyền phải xác minh danh tính rồi khôi phục một **role/profile hiện hữu** theo quy trình có audit; không xóa/reset marker để mở bootstrap lại. Các can thiệp DB trực tiếp cần change-control riêng và có thể bỏ qua guard/audit ở API.
5. ADMIN đăng nhập → **Quản lý tài khoản**, tạo HR (`HR_RECRUITER`) và HM (`HIRING_MANAGER`) khác nhau, hoặc quản lý trạng thái/role. Có thể cấp ADMIN bổ sung; ADMIN và HR Lead có quyền rộng. Admin xác minh email rồi chuyển mật khẩu tạm qua kênh an toàn; hệ thống yêu cầu người nhận đăng nhập và tự đổi mật khẩu (ít nhất 12 ký tự, tối đa 72 byte UTF-8 và đáp ứng chính sách Supabase nếu chặt hơn) trước khi dùng API nghiệp vụ. Sau đổi mật khẩu hoặc khóa/mở tài khoản, app chặn token cũ theo `iat`; đăng nhập mới có thể cần chờ vài giây. Các kiểm tra này nằm ở **API app**, không thay thế kiểm soát truy cập Supabase REST/Storage trực tiếp. Không mở các view/bucket/policy cho browser để bỏ qua API.
6. Thay đổi role HR/HM qua app thu hồi phân công vị trí tương ứng; khi bỏ role cuối cùng cho phép làm HR (`ADMIN`, `HR_LEAD`, `HR_RECRUITER`), app cũng thu hồi mọi phân công HR của tài khoản, kể cả phân công tạo khi còn là Admin/HR Lead. Cấp lại role **không tự khôi phục** phân công. Khóa/mở tài khoản giữ phân công và share để có thể tiếp tục khi mở lại; link CV đã ký vẫn có thể sống tới 10 phút. Granular access grants cấp ngoài app vẫn cần được DBA rà soát. Chưa có UI đổi HM của vị trí đã tạo, mời email, quên/reset mật khẩu, đổi email hay xóa user; cần quy trình được phê duyệt để xử lý các trường hợp này, không tự sửa DB mù quáng.
7. Auth và database không có transaction chung. Khi lỗi xảy ra **trước** DB commit, backend thử xóa Auth identity mới; lỗi mạng/commit không xác định có thể để lại Auth user mồ côi hoặc user đã tạo thành công. Nếu nhận lỗi “không xác nhận được”, **không thử liên tục và không xóa mù**: người vận hành kiểm tra cả Auth, profile/role, marker và log ID tổng hợp; xác minh chính xác identity, tác động rồi reconcile/xóa hoặc hoàn thiện theo change-control. Password và mã setup không được ghi audit.
8. Smoke test bằng dữ liệu giả: ADMIN xem tài khoản/role, tạo HR và HM, xác nhận HR/HM đổi mật khẩu và người không phải ADMIN bị từ chối trang/API quản trị. Admin tạo phòng ban với mã định dạng (ví dụ `REQ-IT-{SEQ:000}`); HR tạo vị trí bằng cách chọn phòng ban ở đầu biểu mẫu—mã vị trí tự sinh—và chọn HM từ danh sách HM đang hoạt động đã tải sẵn, khác mình; HR rồi HM duyệt; kiểm tra không tự duyệt được cả hai bước. Kiểm tra AI config/worker health, upload CV giả, ranking, HR notes và chia sẻ summary-only. Đây là kiểm thử bắt buộc tại môi trường đích, chưa được thực hiện ở đây.
9. Thiết lập backup PostgreSQL và hai bucket, mã hóa, thử restore; giám sát liveness, readiness, worker, queue, ổ đĩa, TLS và chi phí model. Xem [runbook recovery](../DEPLOYMENT.md#phục-hồi-worker-và-giám-sát). Rà/xóa dữ liệu nhạy cảm trước khi chia sẻ log.

## 8. Cập nhật, rollback và sự cố

- Bật maintenance/ngừng nhận job mới; cho PENDING/PROCESSING hoàn tất, kiểm tra queue và **drain tất cả backend/worker cũ** trước migration hoặc rollout. Không chạy worker cũ đồng thời với worker mới; worker cũ không có advisory lock. Backup và thử restore DB/Storage trước thay đổi.
- Trên bản checkout sạch, `git fetch origin`, chọn SHA đã duyệt rồi dùng lại hai file Compose để `up -d --build`; kiểm tra health, version, queue và smoke test giả trước mở traffic. Không scale backend hoặc chạy thêm worker tùy tiện khi chưa đánh giá tài nguyên, kết nối DB và quy trình recovery.
- Nếu lỗi, giữ maintenance, dừng/drain worker mới và làm theo kế hoạch rollback đã thử. Không tự chạy phiên bản cũ trên job mới hoặc reset migration/DB; khôi phục từ backup có thể làm mất dữ liệu mới và cần phê duyệt. Không xóa volume/bucket để “sửa nhanh”.
- Đọc [DEPLOYMENT.md](../DEPLOYMENT.md) cho health, at-least-once, kết nối session, CV link còn hiệu lực sau revoke và thu gom orphan an toàn. Mã chưa hoàn tất retention/xóa, audit bất biến hay bảo vệ token khỏi XSS; xử lý các rào cản này trước production.
