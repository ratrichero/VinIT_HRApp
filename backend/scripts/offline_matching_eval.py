#!/usr/bin/env python3
"""Run local JSON-only synthetic/diagnostic reports; never connects to providers or DB."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.offline_matching_eval import (  # noqa: E402
    ContractError, retrieval_report, shadow_report, strict_repeatability, validate_labels,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("repeatability", "retrieval", "shadow", "labels"))
    parser.add_argument("input", help="JSON input; never place real CVs or secrets in Git")
    parser.add_argument("--output", help="Write report to this path")
    parser.add_argument("--check", action="store_true", help="Fail closed unless repeatability is PASS")
    args = parser.parse_args()
    if args.check and args.mode != "repeatability":
        parser.error("--check is only available for repeatability; other modes are diagnostic")
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ContractError("top-level input must be an object")
        fn = {"repeatability": strict_repeatability, "retrieval": retrieval_report,
              "shadow": shadow_report, "labels": validate_labels}[args.mode]
        report = fn(payload)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 2 if args.check and report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
