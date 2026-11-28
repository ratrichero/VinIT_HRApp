#!/usr/bin/env bash
# Dựng một PostgreSQL dùng-một-lần để chạy 187 integration test.
#
# Vì sao có script này: cách dựng trước đây nằm trong backend/tests/README.md
# và trong CI, hai chỗ khác nhau và đều phải nhớ một chi tiết dễ quên —
# bỏ qua migration 00035. Ba agent mới tự mò theo README (đã lỗi thời, dừng ở
# 00026) sẽ ra ba kiểu sai khác nhau. Script này là một nguồn duy nhất.
#
# An toàn: script chỉ tạo DB mới có tên kết thúc bằng _test và từ chối chạy
# nếu DB đó đã tồn tại. Không bao giờ trỏ tới Supabase: conftest.py cũng sẽ
# chặn ở tầng Python, nhưng chặn ở đây thì lỗi lộ ra sớm hơn và rõ hơn.
#
# Dùng:
#   bash scripts/test-db.sh                       # cổng 55432, DB hra_phase1_test
#   bash scripts/test-db.sh --port 55433 --name hra_a_test
#   eval "$(bash scripts/test-db.sh --export)"    # in ra export TEST_DATABASE_URL
set -euo pipefail

PORT=55432
HOST=127.0.0.1
NAME=hra_phase1_test
USER=postgres
EXPORT_ONLY=0

# Số test mà bộ backend thực sự chạy khi có DB. Trước đây dòng cuối script ghi
# cứng 671 — số của thời còn ít test hơn — nên người chạy thấy 919 dễ tưởng
# mình dựng DB sai. Đo trên DB do chính script này tạo (DB trắng, áp đủ
# migration), ngày 2026-11-28; chi tiết môi trường in ra ở cuối script.
# Không có DB thì kết quả là 732 passed, 187 skipped — 187 chính là số test cần
# DB. Sửa số này khi số test đổi — đừng để nó lệch khỏi thực tế lần nữa.
EXPECTED_PASSED=919

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --user) USER="$2"; shift 2 ;;
    --export) EXPORT_ONLY=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Tham số lạ: $1" >&2; exit 2 ;;
  esac
done

# Tên DB phải kết thúc _test: đây là điều conftest.py cưỡng chế, kiểm sớm cho rõ.
case "$NAME" in
  *_test) ;;
  *) echo "Tên DB phải kết thúc bằng _test (đang là: $NAME)" >&2; exit 2 ;;
esac

# Chặn host không phải cục bộ — không cho ai vô tình trỏ vào Supabase.
case "$HOST" in
  127.0.0.1|localhost|::1) ;;
  *) echo "Chỉ dùng host cục bộ, không dùng: $HOST" >&2; exit 2 ;;
esac

URL="postgresql://${USER}@${HOST}:${PORT}/${NAME}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$EXPORT_ONLY" = "1" ]; then
  echo "export TEST_DATABASE_URL='${URL}'"
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "Thiếu psql. Trên máy: cài postgresql-client. Trong CI: job backend-integration." >&2
  exit 1
fi

# Từ chối ghi đè DB đã có: chạy hai lần lên cùng DB sẽ gặp migration đã áp.
if psql "$URL" -tAc 'SELECT 1' >/dev/null 2>&1; then
  echo "DB ${NAME} đã tồn tại — dùng --name khác, hoặc xoá nó trước nếu chắc chắn." >&2
  exit 1
fi

echo "Tạo ${NAME} trên ${HOST}:${PORT} …"
createdb -h "$HOST" -p "$PORT" -U "$USER" "$NAME"

echo "Tạo role stub và schema auth …"
psql "$URL" -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END $$;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id UUID PRIMARY KEY, email TEXT UNIQUE);
CREATE FUNCTION auth.uid() RETURNS UUID LANGUAGE sql STABLE AS $$ SELECT NULL::UUID $$;
SQL

echo "Áp migration theo thứ tự tên file …"
for migration in "$ROOT"/supabase/migrations/*.sql; do
  base="$(basename "$migration")"
  # 00035 là migration xoá dữ liệu một lần của vòng demo, không phải thay đổi
  # lược đồ. Nó có chốt chặn đòi schema sao lưu app_backup_20261119 — không
  # migration nào tạo schema đó — nên luôn ném lỗi trên DB trắng. Bỏ qua.
  case "$base" in
    00035_*) echo "  bỏ qua ${base} (xoá dữ liệu một lần, cần app_backup_20261119)"; continue ;;
  esac
  psql "$URL" -v ON_ERROR_STOP=1 -q -f "$migration" || {
    echo "Migration lỗi: ${base}" >&2; exit 1; }
done

echo
echo "Xong. Chạy test bằng:"
echo "  export TEST_DATABASE_URL='${URL}'"
echo "  python -m pytest backend/tests -q"
echo
echo "Kỳ vọng: ${EXPECTED_PASSED} passed, 0 skipped (nếu còn skipped thì DB chưa dựng đúng)."
echo "Con số này đo trên DB trắng vừa dựng bởi chính script này (ngày 2026-11-28):"
echo "  PostgreSQL 16.2 + pgvector 0.6.2 của bundle pgserver (scripts/local-pg.sh), cục bộ."
echo "  Không export TEST_DATABASE_URL thì kết quả là 732 passed, 187 skipped."
echo "CI chạy PostgreSQL 17 + pgvector 0.8.x nên số có thể lệch — khi hai bên"
echo "khác nhau, log job backend-integration là chuẩn, không phải dòng này."
