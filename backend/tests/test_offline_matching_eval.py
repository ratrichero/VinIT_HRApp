from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.offline_matching_eval import (
    ContractError, retrieval_report, shadow_report, strict_repeatability, validate_labels,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "staging/synthetic/offline_matching"


def fixture(name):
    return json.loads((FIXTURES / f"{name}_example.json").read_text(encoding="utf-8"))


def test_explicit_rank_snapshots_reuse_and_distinct_forced_runs():
    data = fixture("repeatability")
    report = strict_repeatability(data)
    assert report["status"] == "PASS"
    assert report["ranking"]["kendall_tau"] == 1
    assert report["unranked_baseline"] == ["c"]
    assert report["reuse"] == {"eligible": 3, "reused": 3}
    data["candidate"]["assessments"][0]["assessment_fingerprint"] = "changed-date-fp"
    assert strict_repeatability(data)["fingerprints_changed"] == ["a"]


def test_missing_data_reuse_ranking_and_null_scores_fail_closed():
    data = fixture("repeatability")
    data.pop("reuse")
    assert strict_repeatability(data)["status"] == "INSUFFICIENT_DATA"
    data = fixture("repeatability")
    data["baseline"]["assessments"][0]["matching_score"] = None
    assert strict_repeatability(data)["status"] == "INSUFFICIENT_DATA"
    data = fixture("repeatability")
    data["candidate"]["ranked_application_ids"].remove("b")
    data["candidate"]["unranked_application_ids"].append("b")
    with pytest.raises(ContractError, match="eligibility"):
        strict_repeatability(data)


@pytest.mark.parametrize("change", ["position", "cohort", "criterion", "duplicate", "same_run", "input"])
def test_snapshot_rejects_mixed_or_invalid_cohort(change):
    data = fixture("repeatability")
    c = data["candidate"]
    if change == "position":
        c["position_id"] = "other"
    elif change == "cohort":
        c["cohort_id"] = "other"
    elif change == "criterion":
        c["assessments"][0]["criterion_results"][0]["category"] = "NICE_TO_HAVE"
    elif change == "duplicate":
        c["assessments"].append(copy.deepcopy(c["assessments"][0]))
    elif change == "same_run":
        c["assessments"][0]["assessment_id"] = data["baseline"]["assessments"][0]["assessment_id"]
    else:
        c["assessments"][0]["comparison_input_id"] = "different"
    with pytest.raises(ContractError):
        strict_repeatability(data)


def test_mandatory_flip_requires_review_and_fails_threshold():
    data = fixture("repeatability")
    data["candidate"]["assessments"][0]["criterion_results"][0]["outcome"] = "NO_MATCH"
    report = strict_repeatability(data)
    assert report["status"] == "FAIL"
    assert report["mandatory_review"] == [{"application_id": "a", "criterion_id": "python"}]


def test_retrieval_micro_recall_and_invalid_gold():
    data = fixture("retrieval")
    report = retrieval_report(data)
    assert report["metrics"]["lexical"]["recall_at_5"] == pytest.approx(1 / 3, abs=.000001)
    assert report["metrics"]["merged"]["recall_at_5"] == 1
    assert report["metrics"]["lexical"]["hit_rate_at_5"] == .5
    data["cases"][0]["gold_chunk_ids"] = []
    with pytest.raises(ContractError):
        retrieval_report(data)
    assert retrieval_report({"cases": []})["status"] == "INSUFFICIENT_DATA"


def test_shadow_is_simulation_and_preserves_gates():
    data = fixture("shadow")
    report = shadow_report(data)
    group = report["groups"][0]
    assert group["baseline_ranked"][:2] == ["a", "b"]
    assert group["hypothetical_active_ranked"][:2] == ["b", "a"]
    assert group["unranked"] == ["c"]
    assert group["gate_violations"] == 0
    data["groups"][0]["ranked_application_ids"][:2] = ["b", "a"]
    with pytest.raises(ContractError, match="SHADOW policy"):
        shadow_report(data)


def test_label_contract_rejects_weak_missing_features_and_position_leakage():
    data = fixture("labels")
    assert validate_labels(data)["label_source"] == "SYNTHETIC"
    data["label_source"] = "WEAK"
    with pytest.raises(ContractError):
        validate_labels(data)
    data = fixture("labels")
    data["examples"][0]["features"].pop("matching_score")
    with pytest.raises(ContractError):
        validate_labels(data)
    data = fixture("labels")
    data["examples"][1]["group_id"] = "another-group"
    with pytest.raises(ContractError, match="multiple groups"):
        validate_labels(data)


def test_cli_check_never_accepts_missing_reuse(tmp_path):
    data = fixture("repeatability")
    data.pop("reuse")
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run([sys.executable,
                             str(ROOT / "backend/scripts/offline_matching_eval.py"),
                             "repeatability", str(path), "--check"], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "INSUFFICIENT_DATA"


def test_small_top10_sample_and_provider_fallback_are_not_quality_passes():
    data = fixture("repeatability")
    for snapshot in (data["baseline"], data["candidate"]):
        snapshot["assessments"] = snapshot["assessments"][:3]
        snapshot["ranked_application_ids"] = ["a", "b"]
    assert strict_repeatability(data)["status"] == "INSUFFICIENT_DATA"
    retrieval = fixture("retrieval")
    for case in retrieval["cases"]:
        case["semantic_candidates"] = []
    metrics = retrieval_report(retrieval)["metrics"]
    assert metrics["lexical"] == metrics["merged"]


def test_legacy_cli_check_is_diagnostic_only(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"runs": []}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "backend/scripts/evaluate_matching.py"),
                             str(path), "--check"], capture_output=True, text=True)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert report["acceptance_status"] == "INSUFFICIENT_DATA"


def test_repeatability_detects_status_change_even_when_score_and_criteria_match():
    data = fixture("repeatability")
    data["candidate"]["assessments"][0]["matching_status"] = "NEEDS_HR_VERIFICATION"
    report = strict_repeatability(data)
    assert report["status"] == "FAIL"
    assert report["status_changes"] == ["a"]
