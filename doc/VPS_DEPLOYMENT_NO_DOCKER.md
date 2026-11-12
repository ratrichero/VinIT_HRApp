# Triển khai VinUni HRApp trên VPS không dùng Docker

> **Cập nhật migration 00019:** Các hướng dẫn bật/tắt bằng biến môi trường trong tài liệu lịch sử bên dưới không áp dụng cho worker mới. Xem [AI_ADMIN_ROUTING_STATUS.md](AI_ADMIN_ROUTING_STATUS.md) về database control, giới hạn OFF và rollout/rollback không mixed-version. Code `5f5c529` đã deploy VPS test theo log người dùng; chưa chứng minh production readiness.

> Hướng dẫn này dành cho **staging/pilot với dữ liệu tổng hợp**, chạy trực tiếp bằng Python/Node trên Ubuntu và quản lý hai tiến trình ứng dụng bằng **PM2** (không tạo unit `systemd` cho backend/frontend). Đây chưa phải chứng nhận production. Supabase Auth/Storage thật, OCR, model thật và quy trình vận hành vẫn phải được kiểm thử đầu-cuối trong môi trường đích. Không dùng CV thật trước khi hoàn tất phê duyệt bảo mật/pháp lý, retention, backup/restore và đánh giá AI. Không đưa secret vào Git, log, ticket hay chat.

Tài liệu này thay cách chạy bằng Docker trong [`VPS_DEPLOYMENT.md`](VPS_DEPLOYMENT.md) bằng tiến trình native. Các yêu cầu về migration, quyền database, bảo mật và bootstrap vẫn tuân theo [`../DEPLOYMENT.md`](../DEPLOYMENT.md).

## 1. Kiến trúc

```text
Trình duyệt -- HTTPS :443 --> Nginx trên VPS
                                  |
                                  v
                         Next.js 127.0.0.1:3005
                                  |
                                  | proxy server-side /v1
                                  v
                         FastAPI 127.0.0.1:8005
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
          Supabase PostgreSQL/Auth/Storage   LLM endpoint được phê duyệt
```

- Chỉ Nginx nghe public trên cổng 80/443.
- Frontend chạy ở `127.0.0.1:3005`, backend chạy ở `127.0.0.1:8005`; không mở hai cổng này qua firewall.
- Backend là tiến trình duy nhất giữ `DATABASE_URL`, service-role key và JWT secret.
- Browser gọi `/v1` cùng origin; Next.js proxy sang backend ở phía server nên browser không cần biết địa chỉ backend.
- PM2 quản lý đúng hai app: `hra-backend` và `hra-frontend`, mỗi app một tiến trình (`instances: 1`, `exec_mode: 'fork'`).
- Worker xử lý nền chạy **trong cùng tiến trình backend**. Vì vậy backend chỉ chạy một tiến trình Uvicorn với `--workers 1`; không tăng `instances`/cluster trong PM2.
- Supabase và LLM là dịch vụ bên ngoài VPS, trừ khi LLM/Ollama được cài riêng trên chính VPS này.

## 2. Cần bao nhiêu file env?

Repo có ba file **mẫu** khác nhau vì repo hỗ trợ ba cách nạp cấu hình khác nhau. Các file đã điền giá trị thật đều bị Git bỏ qua; không phải lúc nào cũng phải dùng cả ba.

| File mẫu trong repo | File thật tương ứng | Ai đọc? | Khi chạy không Docker có cần không? |
|---|---|---|---|
| `.env.example` ở thư mục gốc | `.env` ở thư mục gốc | Docker Compose: nạp vào backend và nội suy các biến `HRA_*` | **Không.** Đây là file riêng cho Docker Compose. |
| `backend/.env.example` | `backend/.env` | FastAPI/Pydantic Settings của backend | **Có.** Đây là nguồn cấu hình/secret duy nhất cho backend; PM2 không khai báo lại các secret này. |
| `frontend/.env.local.example` | `frontend/.env.local` | Next.js khi chạy frontend trực tiếp | **Không cần nếu đã đặt trong PM2 ecosystem.** Chỉ chứa `API_INTERNAL_URL`, không phải secret. |

### Cách hiểu đúng

1. **Backend có nhiều biến nhất** vì chỉ backend mới được kết nối PostgreSQL, Supabase Auth/Storage và LLM. Vì lý do đó, các secret nằm trong env của backend.
2. **Frontend gần như không có cấu hình** vì browser dùng `/v1` cùng origin. Frontend chỉ cần biết backend ở đâu qua `API_INTERNAL_URL` ở phía server.
3. **File gốc cho Docker bị trùng nhiều biến với file backend** vì Docker Compose dùng một file gốc để truyền cùng bộ cấu hình vào container backend; còn khi chạy trực tiếp, backend phải có file của riêng nó. Đây là trùng lặp để phục vụ hai chế độ chạy, không phải ba tiến trình cùng đọc ba file.
4. **Không chép secret của backend sang frontend.** Dù có thể gộp mọi biến vào một file hệ thống duy nhất, việc đó làm frontend có khả năng đọc cả `DATABASE_URL` và service-role key nếu cấu hình sai. Tách theo quyền tối thiểu an toàn hơn.

### Bộ cấu hình tối thiểu khi không dùng Docker

Chỉ cần hai nhóm:

- một file env cho backend, ví dụ `backend/.env`;
- một biến `API_INTERNAL_URL=http://127.0.0.1:8005` cho frontend, đặt trong file PM2 ecosystem ở mục 9, nên không cần thêm `frontend/.env.local`.

Không tạo `.env` ở thư mục gốc trong hướng dẫn này, trừ khi sau này quay lại Docker Compose.

## 3. Điều kiện trước khi cài

- VPS Ubuntu 24.04 LTS, quyền `sudo`, SSH đang hoạt động.
- DNS của domain, ví dụ `hr.example.com`, đã trỏ tới IP VPS. Nếu có bản ghi AAAA thì IPv6 của VPS cũng phải hoạt động.
- Ước lượng ban đầu: 2 vCPU, 4 GB RAM, 30 GB ổ đĩa cho app/OCR thử nghiệm. LLM chạy local thường cần thêm RAM/VRAM đáng kể; build frontend cũng có thể tốn RAM.
- Project Supabase đã chuẩn bị PostgreSQL, Auth và hai bucket private `cv-originals`, `cv-extracted-text`.
- Backend hiện tại phụ thuộc migration `00005`–`00010`, gồm `00009_structured_requirement_specs.sql` và `00010_pgvector_bge_ltr.sql`. Project `myrymlqdbyqmpynesiwk` đã áp 00009 ở version remote `20261107021622` và 00010 ở version remote `20261107022845` ngày 07/11/2026; môi trường khác phải đối chiếu và xin phê duyệt migration riêng, không chạy `supabase db push`/reset mù quáng.
- Một LLM endpoint tương thích OpenAI đã được phê duyệt. Nếu chưa có model reachable từ backend thì có thể deploy web/API, nhưng không chạy được xử lý AI.
- Backend xác minh access token theo `alg` trong JWT: token bất đối xứng (ví dụ `ES256`) được kiểm tra bằng JWKS tại `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` kèm `iss`/`aud`; token `HS256` legacy tiếp tục được kiểm tra bằng `SUPABASE_JWT_SECRET` trong thời gian chuyển đổi.
- Service-role key từng lộ trong lịch sử Git vẫn là việc bảo mật riêng phải thu hồi theo kế hoạch trong `DEPLOYMENT.md`; tạo key mới không tự thu hồi key legacy.

## 4. Cài gói hệ thống

Cài Python, Node.js, Nginx, Certbot và các thư viện hệ thống cho OCR/xử lý tài liệu:

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl git nginx certbot python3-certbot-nginx \
  python3 python3-venv python3-pip build-essential \
  tesseract-ocr tesseract-ocr-eng poppler-utils libmagic1 libreoffice-writer
```

Backend yêu cầu Python `>=3.11`; Python mặc định của Ubuntu 24.04 đáp ứng yêu cầu này. Cài Node.js 22 LTS theo hướng dẫn chính thức của NodeSource tại thời điểm triển khai. Sau đó cài PM2 ở phạm vi global để quản lý hai tiến trình ứng dụng:

```bash
sudo npm install --global pm2
python3 --version
node --version
npm --version
pm2 --version
nginx -v
```

Các gói `tesseract-ocr`, `poppler-utils`, `libmagic1` và `libreoffice-writer` tương ứng với dependency hệ thống mà bản Docker từng cài cho OCR và đọc PDF/DOCX. Thiếu chúng, API vẫn có thể khởi động nhưng xử lý một số định dạng CV sẽ lỗi.

Mở firewall theo chính sách của nhà cung cấp và hệ điều hành. Nếu dùng UFW qua SSH, phải cho phép **cổng SSH đang dùng trước** rồi mới bật:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Không mở public cổng 3005 hoặc 8005.

## 5. User và thư mục chạy của hệ thống

Hệ thống này dùng cố định:

| Hạng mục | Giá trị |
|---|---|
| User vận hành/chạy app | `ubuntu` |
| Thư mục gốc của hệ thống | `/home/ubuntu/hra` |
| Backend | `/home/ubuntu/hra/backend` |
| Frontend | `/home/ubuntu/hra/frontend` |
| PM2 process list/log | `/home/ubuntu/.pm2` (mặc định theo home của `ubuntu`) |

Kiểm tra và chuẩn hóa quyền sở hữu:

```bash
id ubuntu
sudo install -d -o ubuntu -g ubuntu -m 0750 /home/ubuntu/hra
sudo install -d -o ubuntu -g ubuntu -m 0750 /home/ubuntu/hra/storage
ls -ld /home/ubuntu/hra /home/ubuntu/hra/storage
whoami   # kỳ vọng: ubuntu
```

Toàn bộ lệnh `git`, `pip`, `npm`, `pm2` trong tài liệu này chạy trực tiếp bằng user `ubuntu`, **không dùng `sudo pm2`**. Dùng `sudo` với PM2 sẽ tạo process list/daemon thuộc root và làm các lệnh `pm2 status` sau đó không thấy đúng hai app. Chỉ dùng `sudo` cho tác vụ hệ thống như cài package, Nginx, Certbot và phân quyền thư mục.

Nếu cần Git SSH deploy key, dùng key riêng chỉ có quyền đọc repo trong `/home/ubuntu/.ssh` theo quy trình quản lý khóa của tổ chức. Không đưa personal access token vào URL clone hoặc shell history.

## 6. Lấy mã theo commit đã duyệt

Luôn deploy một commit SHA đã review, không tự động lấy đầu nhánh đang thay đổi:

```bash
APP_DIR=/home/ubuntu/hra
REPO_URL='git@github.com:ratrichero/VinIT_HRApp.git'
RELEASE_SHA='THAY_BANG_COMMIT_SHA_DA_DUYET'

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
git fetch origin
git checkout --detach "$RELEASE_SHA"
git rev-parse HEAD
```

Thay `REPO_URL` bằng địa chỉ repo thực tế nếu khác.

## 7. Chuẩn bị CA và file env duy nhất cho backend

### 7.1. CA của PostgreSQL

Tải certificate/CA của Supabase qua kênh nhà cung cấp đã xác thực, kiểm tra theo quy trình của tổ chức rồi cài lên VPS:

```bash
sudo install -m 0644 /duong/dan/da/xac-thuc/supabase-db-ca.crt \
  /etc/vinit-hrapp/supabase-db-ca.crt
```

Khi không dùng Docker, đường dẫn trong `DATABASE_URL` phải là đường dẫn **trên VPS**:

```text
/etc/vinit-hrapp/supabase-db-ca.crt
```

Không dùng đường dẫn `/run/secrets/supabase-db-ca.crt`; đó là đường dẫn mount bên trong container của bản Docker.

### 7.2. Tạo `backend/.env`

```bash
cd /home/ubuntu/hra/backend
cp .env.example .env
chmod 600 .env
${EDITOR:-nano} .env
```

Điền giá trị thật trực tiếp trong editor hoặc secret manager. Ví dụ dưới đây chỉ là hình dạng cấu hình, không phải credential hoạt động:

```dotenv
APP_ENV=production
APP_NAME="VinUni HRA API"
DEBUG=false
API_V1_PREFIX=/v1

# Kết nối PostgreSQL trực tiếp qua TLS. URL-encode ký tự đặc biệt trong mật khẩu.
DATABASE_URL=postgresql://DB_USER:URL_ENCODED_PASSWORD@DB_HOST:5432/postgres?sslmode=verify-full&sslrootcert=/etc/vinit-hrapp/supabase-db-ca.crt
DATABASE_POOL_SIZE=5

# Đúng project Supabase. Hai secret dưới đây chỉ nằm ở backend.
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=THAY_BANG_PUBLISHABLE_OR_ANON_KEY_CUA_PROJECT
SUPABASE_SERVICE_ROLE_KEY=THAY_BANG_SECRET_OR_SERVICE_ROLE_KEY_CHI_O_BACKEND
# Chỉ cần trong lúc còn chấp nhận token HS256 legacy; token ES256 dùng JWKS từ SUPABASE_URL.
SUPABASE_JWT_SECRET=

# Để trống. Chỉ đặt tạm trong cửa sổ bootstrap Admin được phê duyệt.
ADMIN_BOOTSTRAP_TOKEN=

STORAGE_BACKEND=supabase
LOCAL_STORAGE_PATH=/home/ubuntu/hra/storage
SUPABASE_STORAGE_BUCKET_CV=cv-originals
SUPABASE_STORAGE_BUCKET_EXTRACTED=cv-extracted-text

LLM_PROVIDER=local
LLM_PROVIDER_NAME=
LLM_MODEL_NAME=llama3.1:8b
LLM_API_BASE=http://127.0.0.1:11434/v1
LLM_API_KEY=
LLM_TEMPERATURE_DEFAULT=0.1
# Điền khóa Fernet đã tạo ở bước chuẩn bị secret bên dưới; chỉ nằm trong backend/.env.
AI_CONFIG_ENCRYPTION_KEY=
LLM_ALLOWED_MODELS=[]
LLM_ALLOWED_API_BASES=[]
ALLOW_EXTERNAL_API=false

MIN_EVIDENCE_COVERAGE=0.7
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
ACCESS_TOKEN_EXPIRE_MINUTES=480
```

Lưu ý quan trọng:

- `LLM_API_BASE=http://127.0.0.1:11434/v1` chỉ đúng nếu Ollama/LLM server chạy **trên cùng VPS**. Nếu model ở máy khác, thay bằng địa chỉ private mà tiến trình backend truy cập được. Khi không dùng Docker, `localhost` nghĩa là chính VPS, không phải container backend.
- Cấu hình AI `ACTIVE` trong database có thể được ưu tiên hơn env. Sau khi có Admin, dùng **Admin → Cấu hình AI** để tạo/kích hoạt cấu hình; không sửa trực tiếp bản ghi ACTIVE bằng SQL. Với `local`/`openai`/`azure`, Admin vẫn chọn endpoint và model nằm trong allowlist. Riêng **OpenAI Compatible**, Admin nhập **tên nhà cung cấp, Base URL, API Key và Model**, bấm **Test kết nối** để kiểm tra trước rồi mới **Tạo và kích hoạt**; API key được mã hóa phía server và không hiển thị lại.
- Sau bước cài backend ở mục 8.1 và trước khi khởi động PM2, tạo khóa mã hóa API key bằng lệnh sau trên VPS, rồi điền giá trị vào `AI_CONFIG_ENCRYPTION_KEY` trong `backend/.env` bằng editor/secret manager. Không đưa giá trị này vào Git, chat hoặc log; nếu để trống, Admin không lưu được API key mới:
  ```bash
  cd /home/ubuntu/hra/backend
  .venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- Model/endpoint mặc định từ env tự được đưa vào allowlist. Các giá trị bổ sung trong `LLM_ALLOWED_MODELS` và `LLM_ALLOWED_API_BASES` phải là JSON array. Allowlist không khóa model/Base URL của OpenAI Compatible tùy chỉnh, nhưng chính sách mạng vẫn áp dụng.
- Không bật `ALLOW_EXTERNAL_API=true` chỉ để thử nhanh. Nếu Base URL OpenAI Compatible là endpoint public như `https://api.openai.com/v1`, phải đặt `ALLOW_EXTERNAL_API=true` sau phê duyệt, dùng HTTPS và có kiểm soát egress/DLP phù hợp; nếu giữ `false`, chỉ endpoint private/loopback reachable mới chạy được.
- Tài khoản trong `DATABASE_URL` phải có quyền nghiệp vụ cần thiết trên `app_private`, đồng thời có quyền `SELECT` trên hai cột `id`, `email` của `auth.users` để quản lý tài khoản. Đây là quyền mạnh, chỉ cấp cho backend theo phê duyệt DBA; service-role API key không tự thay thế tài khoản đăng nhập PostgreSQL.
- Không dùng PgBouncer transaction/statement pooling cho worker. Worker giữ session PostgreSQL và advisory lock trong suốt một attempt; ưu tiên direct connection hoặc session pooler đã được kiểm chứng giữ cùng backend process/session.
- Giữ `SEMANTIC_RETRIEVAL_ENABLED=false` và `LTR_MODE=OFF` như ví dụ cho tới khi có BGE endpoint thật reachable từ tiến trình backend trên VPS, golden set HR và artifact LTR được phê duyệt. Thay các biến này cần restart PM2 backend; không cần restart frontend.

## 8. Cài và build ứng dụng

### 8.1. Backend Python

```bash
cd /home/ubuntu/hra/backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools
.venv/bin/python -m pip install .
```

Kiểm tra nhanh việc nạp cấu hình mà không in secret:

```bash
curl --version >/dev/null
.venv/bin/python -c \
  'from app.core.config import settings; print(settings.APP_ENV, settings.STORAGE_BACKEND)'
```

Không dùng lệnh in toàn bộ `settings` hoặc nội dung `.env` vào log/ticket.

### 8.2. Frontend Next.js

```bash
cd /home/ubuntu/hra/frontend
npm ci --no-audit --no-fund
npm run build
```

Trên VPS/PM2, frontend chạy trực tiếp bằng `next start` từ thư mục `frontend`, nên Next tự phục vụ `.next/static` và `public`; không copy assets vào `.next/standalone`. Bản standalone chỉ còn là lựa chọn riêng cho Docker image khi build với `NEXT_OUTPUT_STANDALONE=1`.

Không cần `frontend/.env.local` nếu biến `API_INTERNAL_URL` đã được đặt trong PM2 ecosystem ở bước tiếp theo. Nếu chạy thử bằng `npm run dev`, khi đó mới sao chép mẫu:

```bash
cp .env.local.example .env.local
```

Hai cách này là **lựa chọn thay thế**, không cần dùng đồng thời.

## 9. Quản lý hai app bằng PM2

PM2 quản lý đúng hai app:

| PM2 app | Tiến trình | Cổng nội bộ |
|---|---|---|
| `hra-backend` | Uvicorn/FastAPI từ Python venv | `127.0.0.1:8005` |
| `hra-frontend` | Next.js `next start` trực tiếp từ thư mục `frontend` | `127.0.0.1:3005` |

Không tạo file `.service` trong `/etc/systemd/system` cho hai app này.

### 9.1. Tạo file PM2 ecosystem

Tạo file `/home/ubuntu/hra/ecosystem.config.cjs` **ngoài Git**; đường dẫn này đã được ignore trong `.gitignore` để smart deploy không coi file cấu hình riêng của VPS là thay đổi mã nguồn. File này không chứa secret của backend:

```js
module.exports = {
  apps: [
    {
      name: 'hra-backend',
      cwd: '/home/ubuntu/hra/backend',
      script: '/home/ubuntu/hra/backend/.venv/bin/python',
      args: '-m uvicorn app.main:app --host 127.0.0.1 --port 8005 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1',
      interpreter: 'none',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      restart_delay: 5000,
      kill_timeout: 30000,
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONDONTWRITEBYTECODE: '1',
      },
    },
    {
      name: 'hra-frontend',
      cwd: '/home/ubuntu/hra/frontend',
      script: '/home/ubuntu/hra/frontend/node_modules/next/dist/bin/next',
      args: 'start --hostname 127.0.0.1 --port 3005',
      interpreter: 'node',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      restart_delay: 5000,
      kill_timeout: 30000,
      env: {
        NODE_ENV: 'production',
        API_INTERNAL_URL: 'http://127.0.0.1:8005',
      },
    },
  ],
};
```

Tạo và phân quyền cho file:

```bash
${EDITOR:-nano} /home/ubuntu/hra/ecosystem.config.cjs
chmod 640 /home/ubuntu/hra/ecosystem.config.cjs
```

Lưu ý:

- Tài liệu này cố định mã nguồn tại `/home/ubuntu/hra`; nếu di chuyển thư mục hệ thống, phải sửa đồng bộ các giá trị `cwd` và `script` trong ecosystem.
- Backend đọc `backend/.env` vì `cwd` của PM2 là thư mục `backend` và Pydantic dùng `env_file=".env"`. Chỉ giữ secret trong `backend/.env`; không chép `DATABASE_URL`, service-role key hoặc JWT secret vào ecosystem.
- `API_INTERNAL_URL` không có `/v1` ở cuối. Route proxy của Next.js sẽ tự ghép `/v1/...` khi chuyển request sang FastAPI ở cổng 8005.
- Không tăng `instances` của backend và không bật cluster mode: worker nền chạy trong tiến trình API, bản vận hành hiện tại dùng một Uvicorn `--workers 1`.

### 9.2. Khởi động và kiểm tra

Chạy bằng user `ubuntu` (không dùng `sudo` cho các lệnh PM2):

```bash
pm2 start /home/ubuntu/hra/ecosystem.config.cjs
pm2 status
pm2 describe hra-backend
pm2 describe hra-frontend

curl --fail --silent --show-error http://127.0.0.1:8005/health
curl --fail --silent --show-error http://127.0.0.1:8005/health/ready
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:3005/
ss -ltnp | grep -E ':(3005|8005) '
```

Kết quả kỳ vọng:

- PM2 hiển thị `hra-backend` và `hra-frontend` ở trạng thái `online`, mỗi app một instance.
- `/health` báo backend đang sống.
- `/health/ready` báo database `connected`. Endpoint này chỉ chứng minh kết nối DB, không chứng minh quyền nghiệp vụ, Auth, Storage hay AI.
- Cổng 3005 và 8005 chỉ xuất hiện ở `127.0.0.1`.

Xem log khi một app lỗi:

```bash
pm2 logs hra-backend --lines 200 --nostream
pm2 logs hra-frontend --lines 200 --nostream
```

Không gửi log có khả năng chứa token, đường dẫn CV hoặc nội dung hồ sơ ra kênh không được phê duyệt.

### 9.3. Lưu danh sách app và tự chạy sau reboot

Sau khi hai app đã `online`, lưu process list của PM2:

```bash
pm2 save
```

Nếu muốn PM2 tự khôi phục hai app sau khi VPS reboot, chạy:

```bash
pm2 startup systemd -u ubuntu --hp /home/ubuntu
```

PM2 sẽ in ra **một lệnh bắt đầu bằng `sudo env PATH=...`**; copy và chạy đúng nguyên văn lệnh đó một lần, sau đó chạy lại:

```bash
pm2 save
```

Lệnh startup chỉ đăng ký **PM2 daemon** với cơ chế khởi động của Ubuntu để PM2 khôi phục process list đã lưu; nó không tạo unit `systemd` riêng cho backend/frontend và không thay cách PM2 quản lý hai app. Nếu không muốn đăng ký tự khởi động, bỏ qua `pm2 startup`; sau reboot phải khôi phục thủ công bằng `pm2 resurrect`.

## 10. Cấu hình Nginx và HTTPS

Tạo `/etc/nginx/sites-available/vinit-hrapp`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name hr.example.com;

    client_max_body_size 260m;
    server_tokens off;

    location / {
        proxy_pass http://127.0.0.1:3005;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_request_buffering off;
        proxy_buffering off;
    }
}
```

Kích hoạt site và kiểm tra:

```bash
sudo ln -s /etc/nginx/sites-available/vinit-hrapp \
  /etc/nginx/sites-enabled/vinit-hrapp
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Cấp chứng chỉ Let's Encrypt và chuyển hướng sang HTTPS:

```bash
sudo certbot --nginx -d hr.example.com --redirect
sudo certbot renew --dry-run
curl --fail --silent --show-error --output /dev/null https://hr.example.com/
```

Kiểm tra từ một máy ngoài VPS:

- `https://hr.example.com` mở được và chứng chỉ hợp lệ.
- Không truy cập trực tiếp được `http://IP-VPS:3005` hoặc `http://IP-VPS:8005`.
- Upload file tổng hợp nhỏ đi qua được `/v1` mà không lỗi giới hạn kích thước của Nginx.

## 11. Bootstrap Admin và smoke test

Chỉ thực hiện phần này khi database của môi trường đích chưa từng có Admin.

1. Kiểm tra bằng quyền DBA:

   ```sql
   SELECT singleton, initialized_at, initialized_by
   FROM app_private.account_initialization;

   SELECT user_id, role_code, revoked_at
   FROM app_private.user_role_assignments
   WHERE role_code = 'ADMIN';
   ```

   Migration cũng đóng bootstrap nếu đã có bất kỳ assignment `ADMIN` nào, kể cả assignment đã thu hồi. Nếu `initialized_at` đã có giá trị, không tìm cách reset marker bằng SQL.

2. Nếu bootstrap còn mở, tạo token ngẫu nhiên mạnh bằng secret manager. Có thể tạo giá trị có ít nhất 32 byte entropy bằng:

   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
   ```

   Không để token xuất hiện trong tài liệu triển khai, ticket hoặc lịch sử lệnh được chia sẻ.

3. Đặt token tạm vào `ADMIN_BOOTSTRAP_TOKEN` trong `backend/.env`, sau đó restart **chỉ backend**:

   ```bash
   pm2 restart hra-backend
   ```

4. Qua HTTPS và mạng/VPN/IP allowlist tin cậy, mở trang đăng nhập của ứng dụng và chọn chức năng khởi tạo Admin đầu tiên. Tạo tài khoản Admin bằng email và mật khẩu do người vận hành quản lý trong secret manager.

5. Xóa token khỏi `backend/.env` rồi restart backend lần nữa:

   ```bash
   pm2 restart hra-backend
   ```

6. Kiểm tra lại `initialized_at` đã được ghi. Từ thời điểm này, việc tạo Admin qua bootstrap phải bị đóng.

Smoke test tối thiểu bằng dữ liệu tổng hợp:

1. Admin tạo một tài khoản HR với role `HR_RECRUITER` và một tài khoản HM với role `HIRING_MANAGER`. HR và HM phải là hai người/tài khoản khác nhau cho hai bước duyệt.
2. Đăng nhập bằng tài khoản mới và xác nhận ứng dụng bắt đổi mật khẩu tạm trước khi vào nghiệp vụ.
3. Admin vào **Quản lý phòng ban**, tạo một phòng ban tổng hợp (ví dụ tên `Phòng Công nghệ thông tin`, mã định dạng `REQ-IT-{SEQ:000}`). Sau đó HR tạo vị trí, chọn phòng ban ở đầu biểu mẫu—mã vị trí phải tự hiện `REQ-IT-001`—và chọn HM từ danh sách đã tải sẵn.
4. Kiểm tra luồng duyệt hai bước HR/HM theo quyền của từng tài khoản.
5. Admin kiểm tra `/v1/admin/worker/health`; xác nhận hàng đợi không có job bị treo bất thường.
6. Upload CV tổng hợp, chờ worker xử lý và kiểm tra trích xuất/chấm điểm bằng model thật đã được kích hoạt.

## 12. Cập nhật và rollback

### 12.1. Cập nhật trong cửa sổ bảo trì

Worker chạy trong backend nên không rollout lẫn tiến trình cũ và mới trên cùng database đang có job.

1. Thông báo cửa sổ bảo trì, ngăn người dùng tạo job mới.
2. Với quyền Admin, kiểm tra `/v1/admin/worker/health`; chờ `processing` và `pending` về trạng thái an toàn theo quy trình vận hành.
3. Dừng frontend rồi backend:

   ```bash
   pm2 stop hra-frontend
   pm2 stop hra-backend
   ```

4. Checkout SHA mới, cài lại dependency và build:

   ```bash
   cd /home/ubuntu/hra
   git fetch origin
   git checkout --detach THAY_BANG_COMMIT_SHA_MOI

   cd backend
   .venv/bin/python -m pip install .

   cd ../frontend
   npm ci --no-audit --no-fund
   npm run build
   ```

5. Nếu release có migration mới, dừng tại đây và thực hiện quy trình migration/staging/backup/rollback đã được phê duyệt riêng. Không tự áp migration chỉ vì code mới đã được checkout. Đối với bản OpenAI Compatible dùng migration `00006`, project Supabase đã kết nối đã được áp version remote `20261106042158`; trên VPS vẫn phải bảo đảm `AI_CONFIG_ENCRYPTION_KEY` đã có trong `backend/.env` trước khi khởi động lại backend, nếu không Admin sẽ không lưu được API key mới. Bản quản lý phòng ban/mã vị trí tự sinh dùng migration `00007`, project đã kết nối đã được áp version remote `20261106050756`; không cần chạy lại migration trên VPS. Bản matching ổn định dùng migration `00008`, project đã kết nối đã được áp version remote `20261107012433`; trên VPS chỉ cần pull code và restart backend/frontend, không chạy lại migration.
6. Khởi động và kiểm tra:

   ```bash
   pm2 start hra-backend
   curl --fail http://127.0.0.1:8005/health/ready
   pm2 start hra-frontend
   curl --fail --output /dev/null http://127.0.0.1:3005/
   curl --fail --output /dev/null https://hr.example.com/
   pm2 save
   ```

### 12.1.1. Cập nhật nhanh bằng `git uphra` trên VPS

Repo có sẵn script smart deploy tại `scripts/deploy.sh`, đã chỉnh theo đúng dự án này:

- PM2 app đúng là `hra-backend` và `hra-frontend`.
- Backend cài dependency từ `backend/pyproject.toml` bằng `backend/.venv`, chỉ khi file này thay đổi.
- Frontend cài dependency bằng `npm ci --no-audit --no-fund`, chỉ khi `frontend/package.json`/`package-lock.json` thay đổi hoặc marker bootstrap chưa có mà `node_modules` không kiểm chứng được.
- Frontend chỉ build lại khi source/config/deps thay đổi; PM2 chạy `next start` trực tiếp từ thư mục `frontend`, nên không copy `.next/static`/`public` vào standalone.
- Script **không tự áp Supabase migrations**. Nếu `supabase/migrations` thay đổi, script dừng lại; sau khi migration đã được áp/kiểm chứng qua quy trình Supabase đã duyệt, chạy lại với `--migrations-verified`.
- Script có stale-guard: nếu lần trước build xong nhưng PM2 restart lỗi, lần chạy sau sẽ retry restart kể cả khi code không đổi.
- Script từ chối pull khi worktree có thay đổi local hoặc local có commit chưa push.

Trên VPS chạy chung nhiều project, không dùng tên chung `git up` cho HRA. Alias đặt bằng `git config --global` thuộc về OS user, không thuộc từng thư mục/repository; nếu NarrativeHealth và HRA cùng khai báo `alias.up`, khai báo sau sẽ thắng trên toàn VPS bất kể đang đứng ở thư mục nào. Vì vậy HRA dùng tên riêng `git uphra`:

```bash
git config --global alias.uphra '!bash /home/ubuntu/hra/scripts/deploy.sh'
```

Có thể giữ nguyên `git up` cho NarrativeHealth, hoặc đổi NarrativeHealth sang một tên riêng tương tự như `git upnh`; không để hai project cùng dùng một global alias trỏ tới hai script khác nhau. PM2 dùng chung một daemon không phải vấn đề tự thân: hai project vẫn an toàn nếu tên process, thư mục chạy, cổng và file env tách riêng. HRA chỉ restart đúng `hra-backend`/`hra-frontend` và dùng cổng 8005/3005.

Cách dùng:

```bash
cd /home/ubuntu/hra
git uphra

# Chỉ định branch deploy khác (hai cách tương đương)
git uphra arena/ea6e2570-vinit-hrapp
bash scripts/deploy.sh --branch arena/ea6e2570-vinit-hrapp

# Buộc làm lại toàn bộ các bước smart deploy
bash scripts/deploy.sh --force

# Sau khi Supabase migrations đã được áp/kiểm chứng ngoài VPS
bash scripts/deploy.sh --migrations-verified
```

Nếu bản script cũ dừng với `worktree has local changes` và chỉ liệt kê `backend/build/` cùng `ecosystem.config.cjs`, không xóa `ecosystem.config.cjs` vì đó là cấu hình PM2 riêng của VPS. Sao lưu file này, chạy một lần `git pull --ff-only origin arena/ea6e2570-vinit-hrapp` thủ công để lấy `.gitignore` và script mới, kiểm tra `git status --short`, rồi chạy lại `git uphra`. Từ bản mới, hai đường dẫn này được ignore và cũng được script bỏ qua ở bước kiểm tra bootstrap.

Khi chuyển từ bản standalone cũ sang `next start` trực tiếp, sao lưu `ecosystem.config.cjs`, sửa riêng app `hra-frontend` theo mục 9.1, rồi xóa/tạo lại đúng process đó trước khi chạy script mới. Cách này làm frontend gián đoạn ngắn nhưng bảo đảm PM2 nhận `cwd`/`script` mới; không dùng `startOrReload` cho thay đổi đường chạy:

```bash
cp -a /home/ubuntu/hra/ecosystem.config.cjs /home/ubuntu/ecosystem.config.cjs.bak-direct
${EDITOR:-nano} /home/ubuntu/hra/ecosystem.config.cjs
pm2 delete hra-frontend
pm2 start /home/ubuntu/hra/ecosystem.config.cjs --only hra-frontend
pm2 save
pm2 describe hra-frontend
curl --fail --output /dev/null http://127.0.0.1:3005/
```

Script mới kiểm tra `pm2 jlist`; nếu `hra-frontend` vẫn trỏ vào `.next/standalone`, script dừng với exit code 6 để tránh restart nhầm runtime cũ sau khi build trực tiếp.

Dòng đầu của script đúng phải in rõ `Smart deploy VinIT HRApp`, đường dẫn repo `/home/ubuntu/hra`, branch cần deploy và `PM2: hra-backend/hra-frontend`. Nếu output vẫn hiển thị `nextjs-dashboard`/`fastapi-backend`, lệnh vừa chạy vẫn là script của NarrativeHealth. Khi đó kiểm tra:

```bash
git config --global --get alias.up
git config --global --get alias.uphra
git remote -v
git branch --show-current
head -25 scripts/deploy.sh
```

Lần chạy đầu tiên trên VPS, nếu chưa có thư mục state `.deploy-state/`, script chỉ coi migration là thay đổi khi lần pull đó thực sự kéo về file migration mới hoặc marker cũ ghi nhận hash khác. Thư mục `.deploy-state/` đã được ignore khỏi Git.

### 12.2. Rollback code

Nếu bản mới lỗi và không phụ thuộc thay đổi database không tương thích ngược:

1. Dừng frontend/backend và drain worker như trên.
2. Checkout lại SHA trước đó.
3. Cài lại backend và build lại frontend trực tiếp như bước cập nhật; không cần thao tác standalone trên VPS.
4. Khởi động backend bằng `pm2 start hra-backend`, kiểm tra `/health/ready` ở cổng 8005, sau đó khởi động frontend bằng `pm2 start hra-frontend`, kiểm tra cổng 3005/HTTPS và chạy `pm2 save`.

Không tự rollback migration bằng cách sửa bảng migration history hoặc chạy reset. Rollback database phải theo kế hoạch đã thử trên staging.

## 13. Vận hành hằng ngày

```bash
# Trạng thái hai app
pm2 status
pm2 describe hra-backend
pm2 describe hra-frontend

# Log trực tiếp
pm2 logs hra-backend
pm2 logs hra-frontend

# Restart sau khi thay backend/.env
pm2 restart hra-backend

# Áp dụng thay đổi trong ecosystem và lưu lại process list
pm2 startOrReload /home/ubuntu/hra/ecosystem.config.cjs --update-env
pm2 save

# Kiểm tra cổng public/loopback
ss -ltnp | grep -E ':(80|443|3005|8005) '
```

- Sao lưu PostgreSQL và hai bucket Supabase theo chính sách của tổ chức; phải thử restore trên staging trước khi coi backup là dùng được.
- Sao lưu an toàn file cấu hình và CA, nhưng không sao lưu secret vào Git hoặc kho không mã hóa.
- Theo dõi dung lượng đĩa vì OCR/libreoffice và file tạm có thể phát sinh dữ liệu lớn.
- Theo dõi `/v1/admin/worker/health` bằng tài khoản Admin và thiết lập giám sát ngoài ứng dụng; endpoint này không tự chứng minh worker còn sống.
- Định kỳ cập nhật Ubuntu, Node.js, Python package và kiểm tra `certbot renew`.
- Nếu đổi env, model allowlist, `ALLOW_EXTERNAL_API`, `AI_CONFIG_ENCRYPTION_KEY` hoặc secret, restart backend bằng PM2 và bảo đảm chỉ có một tiến trình backend dùng cấu hình đó. Nếu sửa ecosystem, dùng `pm2 startOrReload /home/ubuntu/hra/ecosystem.config.cjs --update-env` rồi `pm2 save`. Job đã bắt đầu có thể giữ snapshot cấu hình AI cũ. Không rotate `AI_CONFIG_ENCRYPTION_KEY` nếu chưa có kế hoạch nhập lại API key cho các cấu hình OpenAI Compatible đã lưu.

## 14. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| Backend không start | `.env` sai định dạng, thiếu biến hoặc không kết nối được DB | `pm2 logs hra-backend --lines 200 --nostream` và `pm2 describe hra-backend`; kiểm tra quyền `600`, biến `cwd` và `script` trong ecosystem |
| `/health` được nhưng `/health/ready` lỗi | Sai `DATABASE_URL`, CA, hostname TLS hoặc quyền DB | Kiểm tra đường dẫn `/etc/vinit-hrapp/supabase-db-ca.crt`, `sslmode=verify-full` và kết nối direct/session phù hợp |
| Frontend mở được nhưng API báo 502 | Backend chưa chạy hoặc `API_INTERNAL_URL` sai | `curl http://127.0.0.1:8005/health`; kiểm tra `API_INTERNAL_URL`/`PORT` trong ecosystem rồi `pm2 restart hra-frontend --update-env` |
| Đăng nhập xong quay lại trang login, `/auth/me` trả 401 | Token ES256/RS256 nhưng backend chưa lấy được JWKS, sai `SUPABASE_URL`/issuer, hoặc bản backend đang chạy chưa có hỗ trợ JWKS | Kiểm tra `alg`/`kid` của token, `GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json` từ VPS, log `hra-backend`; restart backend sau khi cập nhật code/env |
| Upload lớn bị Nginx chặn | `client_max_body_size` nhỏ hơn lô CV | Đặt khoảng `260m` và kiểm tra giới hạn app trong backend env |
| OCR/DOCX lỗi | Thiếu gói hệ thống | Kiểm tra `tesseract`, `pdftotext`, LibreOffice và log backend |
| AI không chạy | Model endpoint không reachable, config ACTIVE trỏ loopback/endpoint cũ, dùng OpenAI Compatible public nhưng `ALLOW_EXTERNAL_API=false`, hoặc API key đã lưu không giải mã được | Kiểm tra Base URL/model/API key status trong Admin, `LLM_API_BASE` từ chính VPS, `ALLOW_EXTERNAL_API` và `AI_CONFIG_ENCRYPTION_KEY` trong `backend/.env`; restart `hra-backend` sau khi đổi env |
| Worker không tiến triển | DB session/lock, model/storage lỗi hoặc backend đã dừng | Kiểm tra `/v1/admin/worker/health`, journal backend và kết nối DB; không tự reset job `PROCESSING` |

## 15. Khác biệt cần nhớ so với bản Docker

| Hạng mục | Docker Compose | Không Docker |
|---|---|---|
| File env gốc | Bắt buộc có `.env` ở root | Không dùng |
| Backend env | Compose truyền root `.env` vào container | `backend/.env`; PM2 chỉ đặt biến không chứa secret |
| Địa chỉ backend từ frontend | `http://backend:8000` | `http://127.0.0.1:8005` |
| `localhost` của LLM | Là container backend, thường không phải host | Là chính VPS |
| Đường dẫn CA trong DB URL | `/run/secrets/supabase-db-ca.crt` | `/etc/vinit-hrapp/supabase-db-ca.crt` |
| Quản lý tiến trình | Docker restart policy | PM2: `hra-backend`, `hra-frontend` |
| Cập nhật | Build lại image/container | Cài package, build frontend, restart app bằng PM2 |

Tóm lại: bản không Docker **không cần nhiều file env hơn**. Chỉ backend cần một file env chứa secret; frontend cần đúng một biến địa chỉ backend và biến đó nằm trong PM2 ecosystem, không cần tạo thêm file.
