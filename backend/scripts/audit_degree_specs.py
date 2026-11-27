"""Đếm tiêu chí "bằng cấp" đang thiếu bậc trong DB đã có. CHỈ ĐỌC.

Vì sao cần: từ bản vá audit 2026-11-27, máy **không còn** đoán bậc đại học khi
tiêu chí DEGREE không nêu bậc — tiêu chí đó thành ``unresolved`` cho tới khi HR
điền. Nhưng những dòng đã nằm trong DB từ trước thì vẫn mang ``required_degree_level: null``,
và không migration nào sửa chúng (sửa dữ liệu phải tách riêng, do người điều phối
cấp số). Script này cho biết **phạm vi thật** trước khi ai đó quyết định có cần
một migration sửa dữ liệu hay chỉ cần HR mở từng bộ tiêu chí điền lại.

Chỉ chạy câu SELECT. Không INSERT/UPDATE/DELETE, không tạo migration.

    cd backend && python scripts/audit_degree_specs.py
    cd backend && python scripts/audit_degree_specs.py --json
    cd backend && python scripts/audit_degree_specs.py --samples 20

Dùng cùng ``DATABASE_URL`` với ứng dụng (``app.core.config.settings``). Nếu biến
đó trỏ vào DB dùng chung thì đây vẫn là lệnh chỉ đọc — nhưng hãy đọc kỹ phần
"máy chủ đích" mà script in ra trước khi tin con số.
"""
import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.database import engine  # noqa: E402

# `->>` trả NULL cho cả JSON null lẫn khoá vắng mặt, nên một điều kiện là đủ.
_MISSING_LEVEL = (
    "upper(coalesce(ci.requirement_spec->>'kind', '')) = 'DEGREE' "
    "AND nullif(btrim(coalesce(ci.requirement_spec->>'required_degree_level', '')), '') IS NULL"
)


def _host_of(url: str) -> str:
    """Chỉ in phần máy chủ/tên DB — không in chuỗi kết nối (có thể chứa mật khẩu)."""
    tail = url.split("://", 1)[-1]
    return tail.rsplit("@", 1)[-1]


def collect(samples: int) -> dict:
    with engine.connect() as conn:
        totals = conn.execute(text(f"""
            SELECT
                count(*) FILTER (
                    WHERE upper(coalesce(ci.requirement_spec->>'kind', '')) = 'DEGREE'
                ) AS degree_items,
                count(*) FILTER (WHERE {_MISSING_LEVEL}) AS missing_level
            FROM app_private.criteria_items ci
            WHERE ci.requirement_spec IS NOT NULL
        """)).mappings().one()

        by_status = conn.execute(text(f"""
            SELECT cv.status,
                   count(*) FILTER (WHERE {_MISSING_LEVEL}) AS missing_level,
                   count(*) AS items
            FROM app_private.criteria_items ci
            JOIN app_private.criteria_versions cv
              ON cv.criteria_version_id = ci.criteria_version_id
            WHERE ci.requirement_spec IS NOT NULL
            GROUP BY cv.status
            ORDER BY cv.status
        """)).mappings().all()

        by_position = conn.execute(text(f"""
            SELECT p.position_code, p.title, count(*) AS missing_level
            FROM app_private.criteria_items ci
            JOIN app_private.criteria_versions cv
              ON cv.criteria_version_id = ci.criteria_version_id
            JOIN app_private.positions p ON p.position_id = cv.position_id
            WHERE ci.requirement_spec IS NOT NULL AND {_MISSING_LEVEL}
            GROUP BY p.position_code, p.title
            ORDER BY count(*) DESC, p.position_code
            LIMIT :limit
        """), {"limit": max(1, samples)}).mappings().all()

    return {
        "degree_items": int(totals["degree_items"]),
        "missing_level": int(totals["missing_level"]),
        "by_version_status": [
            {
                "status": row["status"],
                "missing_level": int(row["missing_level"]),
                "items": int(row["items"]),
            }
            for row in by_status
        ],
        "by_position": [
            {
                "position_code": row["position_code"],
                "title": row["title"],
                "missing_level": int(row["missing_level"]),
            }
            for row in by_position
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Đếm tiêu chí DEGREE thiếu bậc (chỉ đọc).")
    parser.add_argument("--json", action="store_true", help="in JSON thay vì bảng")
    parser.add_argument("--samples", type=int, default=10, help="số vị trí liệt kê (mặc định 10)")
    args = parser.parse_args()

    report = collect(args.samples)
    host = _host_of(settings.DATABASE_URL)
    if args.json:
        print(json.dumps({"target": host, **report}, ensure_ascii=False, indent=2))
        return 0

    print(f"Máy chủ đích: {host}")
    print(f"Tiêu chí có requirement_spec kiểu DEGREE : {report['degree_items']}")
    print(f"  trong đó THIẾU bậc (required_degree_level null): {report['missing_level']}")
    if report["by_version_status"]:
        print("\nTheo trạng thái bộ tiêu chí:")
        for row in report["by_version_status"]:
            print(f"  {row['status']:<12} thiếu {row['missing_level']:>4} / {row['items']:>4} tiêu chí")
    if report["by_position"]:
        print("\nVị trí có nhiều tiêu chí thiếu bậc nhất:")
        for row in report["by_position"]:
            print(f"  {row['position_code']:<24} {row['missing_level']:>3}  {row['title']}")
    if report["missing_level"] == 0:
        print("\nKhông có dòng nào cần sửa dữ liệu.")
    else:
        print("\nNhững tiêu chí này giờ chấm ra 'unresolved' cho tới khi HR điền bậc.")
        print("Không có migration nào sửa chúng; cần sửa dữ liệu thì xin số migration từ người điều phối.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
