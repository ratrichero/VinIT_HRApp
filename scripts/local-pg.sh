#!/usr/bin/env bash
# Dựng PostgreSQL cục bộ để chạy integration test, bằng MỘT lệnh, từ máy trắng:
#
#   bash scripts/local-pg.sh                  # cổng 55433, DB hra_agent_test
#   bash scripts/local-pg.sh --port 55434 --name hra_a2_test
#   bash scripts/local-pg.sh --stop           # tắt server, giữ dữ liệu
#
# Vì sao có script này: bước dựng trước đây chỉ nằm trong đầu người vừa làm —
# pip install pgserver, tìm bundle, tự viết hai file extension shim, initdb,
# pg_ctl với cổng riêng, rồi mới gọi scripts/test-db.sh. `/tmp` không sống qua
# archive, nên mỗi phiên sau phải mò lại từ đầu, và mò sai một bước thì triệu
# chứng rất khó đọc (xem "Bẫy" bên dưới).
#
# Script này KHÔNG tạo schema: nó lo phần PostgreSQL (binary, data dir, cổng,
# extension), rồi gọi `scripts/test-db.sh` — nguồn duy nhất của phần tạo DB,
# role stub, schema auth và áp migration. Đừng chép phần đó vào đây.
#
# Khác biệt với CI (PostgreSQL 17 + pgvector/pgvector:pg17):
#   * Ở đây là **PG 16.2** trong bundle của `pgserver` (wheel tự chứa binary,
#     không cần root, không cần cài PostgreSQL hệ thống). PG 17 của CI có
#     pgvector 0.8.x; bundle 16.2 có pgvector **0.6.2** (bản dựng sẵn trong
#     bundle). Test nào dựa vào cú pháp/opclass mới của pgvector ≥ 0.7 có thể
#     xanh trên CI mà đỏ ở đây, hoặc ngược lại — khi nghi ngờ, kiểm bằng CI.
#   * Bundle **không kèm** `uuid-ossp` và `pgcrypto` (đây là phần contrib, cần
#     thư viện hệ thống). Script cài hai shim thuần SQL, xem SHIM bên dưới.
#   * Không có `postgres` user hệ thống, không có socket mặc định: ta tự đặt
#     `-k <sockdir>`. Vì vậy mọi lệnh phải chỉ đúng cổng, đừng dựa vào mặc định.
#   * CI dựng DB bằng `scripts/test-db.sh` trên service container; ở đây cùng
#     script đó nhưng trỏ vào server do ta khởi động.
set -euo pipefail

PORT=55433
NAME=hra_agent_test
USER=postgres
VENV=/tmp/venv
DATA=/tmp/pgdata
LOG=/tmp/pg.log
SOCKDIR=/tmp/pgsock
DO_STOP=0

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --data) DATA="$2"; shift 2 ;;
    --venv) VENV="$2"; shift 2 ;;
    --log) LOG="$2"; shift 2 ;;
    --stop) DO_STOP=1; shift ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Tham số lạ: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Tên DB phải kết thúc _test: conftest.py cưỡng chế điều này, kiểm sớm cho rõ.
case "$NAME" in
  *_test) ;;
  *) echo "Tên DB phải kết thúc bằng _test (đang là: $NAME)" >&2; exit 2 ;;
esac

# ---------- 1. pgserver: bundle PostgreSQL tự chứa -------------------------
# pgserver tải một bản PostgreSQL dựng sẵn vào site-packages của venv. Không
# cần root, không đụng PostgreSQL của hệ thống — đúng thứ cần cho một máy dùng
# chung nhiều agent, nơi ai cũng phải có cổng riêng.
if [ ! -x "$VENV/bin/python" ]; then
  echo "Tạo venv ở ${VENV} và cài pgserver …"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet pgserver
fi

PG="$("$VENV/bin/python" -c 'import os, pgserver; print(os.path.join(os.path.dirname(pgserver.__file__), "pginstall"))')"
if [ ! -x "$PG/bin/pg_ctl" ]; then
  echo "pgserver không có bundle ở ${PG} — cài lại: ${VENV}/bin/pip install --force-reinstall pgserver" >&2
  exit 1
fi
export PATH="$PG/bin:$PATH"
PGVER="$("$PG/bin/postgres" --version | awk '{print $3}')"
echo "PostgreSQL ${PGVER} ở ${PG}"

if [ "$DO_STOP" = "1" ]; then
  if [ -d "$DATA" ] && "$PG/bin/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
    "$PG/bin/pg_ctl" -D "$DATA" -m fast stop
    echo "Đã tắt server ở ${DATA}. Dữ liệu giữ nguyên."
  else
    echo "Không có server nào chạy ở ${DATA}."
  fi
  exit 0
fi

# ---------- 2. Hai shim extension -----------------------------------------
# Bundle là bản PostgreSQL **core**: không có contrib, nên `CREATE EXTENSION
# uuid-ossp` / `pgcrypto` trong migration sẽ lỗi "could not open extension
# control file". Cài bản shim thuần SQL thay vì vá migration (migration đã áp
# lên Supabase thật, không được sửa).
#
# Vì sao shim trung thực chứ không phải giả vờ:
#   * uuid-ossp: `uuid_generate_v4()` vốn là UUID v4 ngẫu nhiên. Core PG 13+ có
#     `gen_random_uuid()`, cùng thuật toán, cùng kiểu trả về — ánh xạ thẳng.
#   * pgcrypto: PG 16 buộc pgcrypto phải liên kết OpenSSL. Máy này chỉ có header
#     OpenSSL 3.5 (của Node) lệch ABI với libcrypto hệ thống, nên không dựng
#     được bản thật. Migration chỉ dùng `digest(data, 'sha256')` và
#     `gen_random_uuid()` (đã có trong core), nên shim cài `digest()` trên
#     `sha256()/sha384()/sha512()/sha224()` của core — cùng thuật toán, cùng
#     byte đầu ra. Nếu sau này migration cần `crypt()`/`pgp_sym_encrypt()`, shim
#     này sẽ **không** đủ và phải dựng pgcrypto thật.
SHIM="$PG/share/postgresql/extension"

install_shim() {  # $1 = tên file, nội dung đọc từ stdin
  if [ -f "$SHIM/$1" ] && [ -s "$SHIM/$1" ]; then
    return 0
  fi
  cat > "$SHIM/$1"
  echo "  + shim ${1}"
}

install_shim uuid-ossp.control <<'EOF'
# Shim cho harness test cục bộ: bundle pgserver không kèm uuid-ossp và không có
# libuuid. uuid_generate_v4() của uuid-ossp vốn là UUID v4 ngẫu nhiên, nên ánh xạ
# sang gen_random_uuid() có sẵn trong core PG13+ là cùng ngữ nghĩa.
comment = 'shim: uuid_generate_v4() -> gen_random_uuid() (core)'
default_version = '1.1'
relocatable = true
EOF

install_shim uuid-ossp--1.1.sql <<'EOF'
CREATE FUNCTION uuid_generate_v4() RETURNS uuid
LANGUAGE sql VOLATILE STRICT PARALLEL SAFE
AS $$ SELECT gen_random_uuid() $$;
EOF

install_shim pgcrypto.control <<'EOF'
# Shim cho harness test cục bộ. Bundle pgserver không kèm pgcrypto; PG16 buộc
# pgcrypto phải có OpenSSL, mà máy này chỉ có header OpenSSL 3.5 (của Node) lệch
# ABI với libcrypto 3.0.13. Migration chỉ dùng digest(...,'sha256') và
# gen_random_uuid() (core), nên shim này cài digest() trên nền sha256()/md5()
# của core — cùng thuật toán, cùng byte đầu ra.
comment = 'shim: digest() tren core sha2 (khong co OpenSSL)'
default_version = '1.3'
relocatable = true
EOF

install_shim pgcrypto--1.3.sql <<'EOF'
CREATE FUNCTION digest(data text, algo text) RETURNS bytea
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE lower(algo)
    WHEN 'sha256' THEN sha256(convert_to(data, 'UTF8'))
    WHEN 'sha384' THEN sha384(convert_to(data, 'UTF8'))
    WHEN 'sha512' THEN sha512(convert_to(data, 'UTF8'))
    WHEN 'sha224' THEN sha224(convert_to(data, 'UTF8'))
    WHEN 'md5'    THEN decode(md5(data), 'hex')
    ELSE NULL
  END
$$;

CREATE FUNCTION digest(data bytea, algo text) RETURNS bytea
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE lower(algo)
    WHEN 'sha256' THEN sha256(data)
    WHEN 'sha384' THEN sha384(data)
    WHEN 'sha512' THEN sha512(data)
    WHEN 'sha224' THEN sha224(data)
    WHEN 'md5'    THEN decode(md5(data), 'hex')
    ELSE NULL
  END
$$;
EOF

# ---------- 3. initdb + pg_ctl trên cổng riêng ----------------------------
# Cổng riêng theo từng agent: nhiều phiên chạy song song trên cùng máy, và
# 5432 thường đã bị PostgreSQL của hệ thống hoặc một agent khác chiếm.
if [ ! -f "$DATA/PG_VERSION" ]; then
  echo "initdb vào ${DATA} …"
  mkdir -p "$(dirname "$DATA")"
  "$PG/bin/initdb" -D "$DATA" -U "$USER" --auth=trust -E UTF8 --locale=C >/dev/null
  echo "  xong (PG $(cat "$DATA/PG_VERSION"), user ${USER}, auth trust — chỉ cục bộ)"
else
  echo "Dùng data dir có sẵn ở ${DATA} (PG $(cat "$DATA/PG_VERSION"))"
fi

mkdir -p "$SOCKDIR" "$(dirname "$LOG")"
if "$PG/bin/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
  echo "Server đã chạy sẵn ở ${DATA}."
else
  echo "Khởi động trên cổng ${PORT} (socket ${SOCKDIR}, log ${LOG}) …"
  "$PG/bin/pg_ctl" -D "$DATA" -l "$LOG" -w \
    -o "-p ${PORT} -k ${SOCKDIR} -h 127.0.0.1" start >/dev/null
fi

for _ in $(seq 1 30); do
  if "$PG/bin/pg_isready" -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! "$PG/bin/pg_isready" -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then
  echo "Server không trả lời trên 127.0.0.1:${PORT}. 20 dòng cuối ${LOG}:" >&2
  tail -20 "$LOG" >&2 || true
  exit 1
fi

# ---------- 4. Giao phần schema cho test-db.sh ---------------------------
# Bẫy đã gặp: nếu server đã chạy nhưng ở cổng khác, test-db.sh sẽ báo "thiếu
# psql" hoặc treo. Kiểm đúng cổng trước khi giao việc, để lỗi lộ ra ở đây.
if psql "postgresql://${USER}@127.0.0.1:${PORT}/postgres" -tAc 'SELECT 1' >/dev/null 2>&1; then
  echo
  bash "$ROOT/scripts/test-db.sh" --port "$PORT" --name "$NAME" --user "$USER"
else
  echo "Không kết nối được postgresql://${USER}@127.0.0.1:${PORT}/postgres" >&2
  echo "Server đang chạy ở data dir ${DATA} nhưng không ở cổng ${PORT}? Tắt bằng --stop rồi chạy lại." >&2
  exit 1
fi

echo "Tắt khi xong: bash scripts/local-pg.sh --data ${DATA} --stop"
echo "Lưu ý: PostgreSQL ${PGVER} + pgvector 0.6.2 ở đây khác PG 17 + pgvector 0.8.x của CI."
