#!/usr/bin/env python3
"""Measure matching repeatability from exported assessment snapshots.

Input JSON may be either:
  * a list of assessment run objects, or
  * {"runs": [...], "reuse": {"eligible": 20, "reused": 20},
     "baseline_ranking": [...], "candidate_ranking": [...]}

Each run should contain application_id, matching_score (or score),
assessment_fingerprint (or fingerprint), and criterion_results/criteria/
findings with criterion_id + outcome.  Runs sharing a fingerprint are
treated as forced reruns: the first occurrence of each application is the
baseline.  Rankings, when not supplied explicitly, are derived from score
(descending), evidence coverage (descending), then application_id. This legacy
report is diagnostic only: --check always fails closed. For acceptance-oriented
comparison of explicit snapshots use offline_matching_eval.py repeatability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evaluation import build_repeatability_report, compare_rankings


def _derived_ranking(runs: list[dict[str, Any]], *, latest: bool) -> list[str]:
    # Runs are ordered explicitly by run_index/created_at before choosing
    # the first (baseline) or latest (candidate) run per application.  The
    # raw file order is only a final tie-breaker, never the chronology.
    from app.services.evaluation import _chronologically_ordered

    selected: dict[str, dict[str, Any]] = {}
    for run in _chronologically_ordered(runs):
        application_id = str(run.get("application_id") or run.get("id") or "")
        if not application_id:
            continue
        if latest or application_id not in selected:
            selected[application_id] = run

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[float, float, str]:
        application_id, run = item
        score = run.get("matching_score", run.get("score"))
        coverage = run.get("evidence_coverage", run.get("coverage"))
        return (
            -(float(score) if score is not None else -1),
            -(float(coverage) if coverage is not None else 0),
            application_id,
        )

    return [application_id for application_id, _ in sorted(selected.items(), key=sort_key)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to an assessment snapshot JSON file")
    parser.add_argument("--output", help="Write the JSON report here instead of stdout")
    parser.add_argument("--check", action="store_true",
                        help="Legacy diagnostic cannot establish acceptance; always exits 2")
    parser.add_argument("--max-p95-score-drift", type=float, default=2.0)
    parser.add_argument("--max-criterion-flip-rate", type=float, default=0.02)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        runs, reuse, rankings = payload, None, {}
    else:
        runs = payload.get("runs", [])
        reuse = payload.get("reuse")
        rankings = payload.get("rankings") or {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        fingerprint = str(run.get("assessment_fingerprint") or run.get("fingerprint") or "unknown")
        grouped.setdefault(fingerprint, []).append(run)
    groups = [
        {"fingerprint": fingerprint, "runs": grouped[fingerprint]}
        for fingerprint in sorted(grouped)
    ]

    baseline_ranking = rankings.get("baseline") or _derived_ranking(runs, latest=False)
    candidate_ranking = rankings.get("candidate") or _derived_ranking(runs, latest=True)
    ranking = compare_rankings(baseline_ranking, candidate_ranking) if runs else None

    report = build_repeatability_report(
        groups,
        reuse_stats=reuse,
        baseline_ranking=baseline_ranking if runs else None,
        candidate_ranking=candidate_ranking if runs else None,
        thresholds={
            "max_p95_score_drift": args.max_p95_score_drift,
            "max_criterion_flip_rate": args.max_criterion_flip_rate,
        },
    )
    if ranking is not None:
        report["ranking"] = ranking

    # Legacy exports do not establish explicit paired ranking snapshots,
    # cohort provenance, or forced-rerun identity. Never certify them.
    report["diagnostic_passed"] = report["passed"]
    report["passed"] = False
    report["diagnostic_only"] = True
    report["acceptance_status"] = "INSUFFICIENT_DATA"
    report["acceptance_note"] = (
        "Legacy input cannot establish acceptance. Use offline_matching_eval.py "
        "repeatability with explicit snapshots and reuse counts."
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 2 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
