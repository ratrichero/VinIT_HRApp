"""Offline synthetic-first evaluation helpers. Never access a database or provider.

These reports are diagnostic. They do not certify a model, dataset or release.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from app.core.config import settings
from app.services.evaluation import compare_assessments, compare_rankings
from app.services.ltr import FEATURE_NAMES
from app.services.matching import MatchingEngine
from app.services.semantic_retrieval import merge_candidate_chunks

STATUSES = {"MEETS_MANDATORY", "NEEDS_HR_VERIFICATION", "POSSIBLE_MISMATCH", "NOT_ASSESSED"}
OUTCOMES = {"STRONG_MATCH", "MATCH", "UNCLEAR", "NO_MATCH"}


class ContractError(ValueError):
    """Input is incomplete or inconsistent; no acceptance can be inferred."""


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _unique_ids(items: Any, field: str) -> list[str]:
    if not isinstance(items, list):
        raise ContractError(f"{field} must be a list")
    ids = [_identifier(item, field) for item in items]
    if len(ids) != len(set(ids)):
        raise ContractError(f"{field} contains duplicate IDs")
    return ids


def _snapshot(snapshot: Any) -> tuple[dict[str, dict], list[str], set[str]]:
    if not isinstance(snapshot, dict):
        raise ContractError("snapshot must be an object")
    for key in ("position_id", "criteria_version_id", "cohort_id", "ranking_run_id", "ranking_policy_version"):
        _identifier(snapshot.get(key), key)
    threshold = snapshot.get("min_evidence_coverage")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ContractError("invalid min_evidence_coverage")
    runs = snapshot.get("assessments")
    if not isinstance(runs, list) or not runs:
        raise ContractError("assessments must be non-empty")
    by_id = {}
    assessment_ids = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ContractError("assessment must be an object")
        app_id = _identifier(run.get("application_id"), "application_id")
        if app_id in by_id:
            raise ContractError("duplicate assessment application_id")
        assessment_id = _identifier(run.get("assessment_id"), "assessment_id")
        if assessment_id in assessment_ids:
            raise ContractError("duplicate assessment_id")
        assessment_ids.add(assessment_id)
        _identifier(run.get("assessment_fingerprint"), "assessment_fingerprint")
        _identifier(run.get("comparison_input_id"), "comparison_input_id")
        if run.get("matching_status") not in STATUSES:
            raise ContractError("invalid or missing matching_status")
        coverage = run.get("evidence_coverage")
        if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or not 0 <= coverage <= 1:
            raise ContractError("invalid evidence_coverage")
        score = run.get("matching_score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100):
            raise ContractError("invalid matching_score")
        criteria = run.get("criterion_results")
        if not isinstance(criteria, list) or not criteria:
            raise ContractError("criterion_results must be non-empty")
        criterion_ids = []
        for criterion in criteria:
            if (not isinstance(criterion, dict) or criterion.get("outcome") not in OUTCOMES
                    or criterion.get("category") not in {"MUST_HAVE", "NICE_TO_HAVE"}):
                raise ContractError("invalid criterion result or category")
            criterion_ids.append(_identifier(criterion.get("criterion_id"), "criterion_id"))
        _unique_ids(criterion_ids, "criterion_ids")
        by_id[app_id] = run
    ranked = _unique_ids(snapshot.get("ranked_application_ids"), "ranked_application_ids")
    unranked = set(_unique_ids(snapshot.get("unranked_application_ids"), "unranked_application_ids"))
    if set(ranked) & unranked or set(ranked) | unranked != set(by_id):
        raise ContractError("ranked/unranked must partition assessments exactly")
    eligible = {key for key, run in by_id.items() if run["evidence_coverage"] >= threshold
                and run["matching_status"] != "NOT_ASSESSED"}
    if set(ranked) != eligible:
        raise ContractError("rank eligibility does not match snapshot coverage/status gate")
    return by_id, ranked, unranked


def strict_repeatability(payload: dict) -> dict:
    """Compare explicit actual rankings, forced-rerun cohorts, and reuse counts.

    comparison_input_id is a caller-supplied frozen provenance ID, not proof
    that two executions really ran; review the source/run metadata separately.
    """
    b, br, bu = _snapshot(payload.get("baseline"))
    c, cr, cu = _snapshot(payload.get("candidate"))
    baseline, candidate = payload["baseline"], payload["candidate"]
    if baseline["ranking_run_id"] == candidate["ranking_run_id"]:
        raise ContractError("baseline and candidate ranking runs must differ")
    for field in ("position_id", "criteria_version_id", "cohort_id", "ranking_policy_version", "min_evidence_coverage"):
        if baseline[field] != candidate[field]:
            raise ContractError(f"snapshot {field} differs")
    missing = sorted(set(b) - set(c))
    extra = sorted(set(c) - set(b))
    if missing or extra:
        return {"status": "INSUFFICIENT_DATA", "missing_in_candidate": missing, "extra_in_candidate": extra}
    for app_id in b:
        if b[app_id]["assessment_id"] == c[app_id]["assessment_id"]:
            raise ContractError("forced rerun requires distinct assessment IDs for " + app_id)
        if b[app_id]["comparison_input_id"] != c[app_id]["comparison_input_id"]:
            raise ContractError("forced rerun inputs differ for " + app_id)
        categories_b = {i["criterion_id"]: i["category"] for i in b[app_id]["criterion_results"]}
        categories_c = {i["criterion_id"]: i["category"] for i in c[app_id]["criterion_results"]}
        if categories_b != categories_c:
            raise ContractError("criterion categories differ for " + app_id)
        if {i["criterion_id"] for i in b[app_id]["criterion_results"]} != {i["criterion_id"] for i in c[app_id]["criterion_results"]}:
            raise ContractError("criterion sets differ for " + app_id)
    # Caller supplies actual ranked order, not a score-derived approximation.
    compared = compare_assessments(b.values(), c.values())
    ranking = compare_rankings(br, cr)
    reuse = payload.get("reuse")
    if not isinstance(reuse, dict):
        reuse = {}
    eligible, reused = reuse.get("eligible"), reuse.get("reused")
    valid_reuse = (type(eligible) is int and type(reused) is int and eligible > 0 and 0 <= reused <= eligible)
    insufficient = []
    if not valid_reuse:
        insufficient.append("reuse_counts")
    if (compared["p95_score_drift"] is None or compared["criterion_flip_rate"] is None
            or any(b[k]["matching_score"] is None or c[k]["matching_score"] is None for k in b)):
        insufficient.append("assessment_metrics")
    if set(br) != set(cr) or len(br) < 10 or ranking["kendall_tau"] is None or ranking["top_k_overlap"]["10"] is None:
        insufficient.append("ranking_metrics_or_ranked_cohort")
    status_changes = sorted(k for k in b if b[k]["matching_status"] != c[k]["matching_status"])
    coverage_changes = {k: round(c[k]["evidence_coverage"] - b[k]["evidence_coverage"], 6)
                        for k in sorted(b) if c[k]["evidence_coverage"] != b[k]["evidence_coverage"]}
    checks = {
        "status_unchanged": not status_changes,
        "reuse": valid_reuse and reused == eligible,
        "p95_drift": compared["p95_score_drift"] is not None and compared["p95_score_drift"] <= 2,
        "criterion_flip": compared["criterion_flip_rate"] is not None and compared["criterion_flip_rate"] <= .02,
        "kendall": ranking["kendall_tau"] is not None and ranking["kendall_tau"] >= .90,
        "top10": ranking["top_k_overlap"]["10"] is not None and ranking["top_k_overlap"]["10"] >= .90,
    }
    review = []
    for app_id in sorted(b):
        base = {item["criterion_id"]: item for item in b[app_id]["criterion_results"]}
        other = {item["criterion_id"]: item for item in c[app_id]["criterion_results"]}
        for criterion_id in base:
            old, new = base[criterion_id], other[criterion_id]
            if old.get("category") == "MUST_HAVE" or new.get("category") == "MUST_HAVE":
                if old["outcome"] != new["outcome"] or "NO_MATCH" in (old["outcome"], new["outcome"]):
                    review.append({"application_id": app_id, "criterion_id": criterion_id})
    return {"status": "INSUFFICIENT_DATA" if insufficient else "PASS" if all(checks.values()) else "FAIL",
            "insufficient": insufficient, "checks": checks, "assessments": compared,
            "ranking": ranking, "unranked_baseline": sorted(bu), "unranked_candidate": sorted(cu),
            "fingerprints_changed": sorted(k for k in b if b[k]["assessment_fingerprint"] != c[k]["assessment_fingerprint"]),
            "status_changes": status_changes, "coverage_changes": coverage_changes,
            "mandatory_review": review, "reuse": reuse,
            "warning": "Diagnostic thresholds; forced rerun provenance and HR review require independent verification."}


def retrieval_report(payload: dict) -> dict:
    """Micro recall and query hit@5 for explicit lexical and merged chunk IDs."""
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        return {"status": "INSUFFICIENT_DATA", "cases": 0}
    counts = {"lexical": Counter(), "merged": Counter()}
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ContractError("retrieval case must be an object")
        case_id = _identifier(case.get("case_id"), "case_id")
        if case_id in seen:
            raise ContractError("duplicate case_id")
        seen.add(case_id)
        universe = set(_unique_ids(case.get("all_chunk_ids"), "all_chunk_ids"))
        gold = set(_unique_ids(case.get("gold_chunk_ids"), "gold_chunk_ids"))
        if not gold or not gold <= universe:
            raise ContractError("gold chunks must be non-empty and belong to this document")
        lexical = _unique_ids(case.get("lexical_chunk_ids"), "lexical_chunk_ids")
        if not set(lexical) <= universe:
            raise ContractError("lexical chunk does not belong to this document")
        semantic = case.get("semantic_candidates")
        if not isinstance(semantic, list):
            raise ContractError("semantic_candidates must be a list, empty for provider fallback")
        semantic_ids = []
        for item in semantic:
            if not isinstance(item, dict):
                raise ContractError("semantic candidate must be an object")
            semantic_ids.append(_identifier(item.get("chunk_id"), "chunk_id"))
            score = item.get("semantic_similarity")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not -1 <= score <= 1:
                raise ContractError("semantic_similarity must be a finite cosine score")
        _unique_ids(semantic_ids, "semantic_candidate_ids")
        if not set(semantic_ids) <= universe:
            raise ContractError("semantic chunk does not belong to this document")
        # Inputs are already the retrieved/top-k candidates; run the exact
        # production merge policy rather than asking the caller to fake it.
        merged = merge_candidate_chunks([{"chunk_id": cid} for cid in lexical], semantic, limit=5)
        for mode, result in (("lexical", lexical), ("merged", [x["chunk_id"] for x in merged])):
            matches = len(gold & set(result[:5]))
            counts[mode].update({"gold": len(gold), "found": matches, "hit_queries": int(matches > 0)})
    metrics = {key: {"recall_at_5": round(c["found"] / c["gold"], 6),
                     "hit_rate_at_5": round(c["hit_queries"] / len(cases), 6),
                     "found": c["found"], "gold": c["gold"], "queries": len(cases)}
               for key, c in counts.items()}
    return {"status": "DIAGNOSTIC", "metrics": metrics,
            "warning": "Chunk IDs are supplied externally; no provider is invoked and no quality gate is implied."}


def shadow_report(payload: dict) -> dict:
    """Simulate ACTIVE from supplied SHADOW snapshots without changing runtime."""
    if not isinstance(payload.get("groups"), list) or not payload["groups"]:
        return {"status": "INSUFFICIENT_DATA", "groups": []}
    reports = []
    seen = set()
    engine = MatchingEngine()
    for group in payload["groups"]:
        apps, ranked, unranked = _snapshot(group)
        if group["min_evidence_coverage"] != settings.MIN_EVIDENCE_COVERAGE:
            raise ContractError("snapshot coverage gate differs from local runtime configuration")
        key = (group["position_id"], group["criteria_version_id"])
        if key in seen:
            raise ContractError("duplicate position/criteria group")
        seen.add(key)
        scores = {}
        applications = []
        for app_id, run in apps.items():
            score = run.get("ltr_score")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ContractError("every assessment requires a finite ltr_score")
            scores[app_id] = float(score)
            applications.append({"application_id": app_id, "latest_assessment": run})
        shadow = engine.rank_applications(applications, [], ltr_scores=scores, ltr_mode="SHADOW")
        shadow_ranked = [x["application_id"] for x in shadow if x["rank_number"] is not None]
        shadow_unranked = {x["application_id"] for x in shadow if x["rank_number"] is None}
        if shadow_ranked != ranked or shadow_unranked != unranked:
            raise ContractError("published ranking does not match SHADOW policy snapshot")
        active = engine.rank_applications(applications, [], ltr_scores=scores, ltr_mode="ACTIVE")
        ar = [x["application_id"] for x in active if x["rank_number"] is not None]
        au = {x["application_id"] for x in active if x["rank_number"] is None}
        # Runtime sorts by status before eligibility, so check status order and
        # coverage eligibility *inside* each status, not across statuses.
        status_order = {"MEETS_MANDATORY": 0, "NEEDS_HR_VERIFICATION": 1, "POSSIBLE_MISMATCH": 2, "NOT_ASSESSED": 3}
        active_keys = [(status_order[x["latest_assessment"]["matching_status"]], x["rank_number"] is None) for x in active]
        violations = int(active_keys != sorted(active_keys)) + int(set(ar) != set(ranked) or au != unranked)
        reports.append({"position_id": key[0], "criteria_version_id": key[1],
                        "baseline_ranked": ranked, "hypothetical_active_ranked": ar,
                        "unranked": sorted(unranked), "gate_violations": violations,
                        "metrics": compare_rankings(ranked, ar)})
    return {"status": "DIAGNOSTIC", "groups": reports,
            "warning": "Simulation only; no model loading, HR quality labels or rollout approval."}


def validate_labels(payload: dict) -> dict:
    """Validate offline LTR label/feature join with explicit snapshot identity."""
    dataset_version = _identifier(payload.get("dataset_version"), "dataset_version")
    source = payload.get("label_source")
    if source not in {"SYNTHETIC", "HR_GOLD"}:
        raise ContractError("label_source must be SYNTHETIC or HR_GOLD; weak labels are not gold")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ContractError("examples must be non-empty")
    seen, position_groups, groups = set(), {}, set()
    for row in examples:
        if not isinstance(row, dict):
            raise ContractError("example must be an object")
        for key in ("position_id", "criteria_version_id", "application_id", "assessment_id", "reviewer_id", "reviewed_at"):
            _identifier(row.get(key), key)
        identity = (row["position_id"], row["criteria_version_id"], row["application_id"])
        if identity in seen:
            raise ContractError("duplicate application in position/criteria")
        seen.add(identity)
        # The same position must never be split into different train/test groups.
        group_id = _identifier(row.get("group_id"), "group_id")
        if position_groups.setdefault(row["position_id"], group_id) != group_id:
            raise ContractError("position appears in multiple groups")
        groups.add(group_id)
        if type(row.get("label")) is not int or row["label"] not in {0, 1, 2, 3}:
            raise ContractError("label must be an integer 0..3")
        if row.get("adjudication_status") not in {"AGREED", "ADJUDICATED"}:
            raise ContractError("label requires agreement or adjudication")
        features = row.get("features")
        if not isinstance(features, dict) or set(features) != set(FEATURE_NAMES):
            raise ContractError("features must match the current LTR feature contract")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in features.values()):
            raise ContractError("features must be finite numbers")
    return {"status": "VALID_CONTRACT", "dataset_version": dataset_version, "label_source": source,
            "examples": len(examples), "groups": len(groups), "positions": len(position_groups),
            "warning": "Structure only; caller-supplied identities, labels, consent and leakage are not verified."}
