"""Learning-to-Rank for assessment ranking.

The production ranker remains the deterministic gate/score/coverage
policy.  LTR is trained offline from labelled examples grouped by
position, evaluated on held-out *groups* (never random rows from the same
position), and may only reorder candidates inside the same mandatory
gate when an artifact passes its recorded quality gates.

Labels derived from operational application statuses are weak labels:
they encode past HR workflow, not a validated relevance judgement.  They
are suitable for a first shadow-mode experiment, not for silently
replacing the published ranking.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

FEATURE_NAMES: tuple[str, ...] = (
    "matching_score",
    "evidence_coverage",
    "strong_match_rate",
    "match_rate",
    "no_match_rate",
    "unclear_rate",
    "rule_decision_rate",
    "llm_decision_rate",
    "avg_evidence_strength",
    "mandatory_no_match",
    "needs_verification",
    "meets_mandatory",
    "possible_mismatch",
)

STATUS_FEATURES = {
    "MEETS_MANDATORY": "meets_mandatory",
    "NEEDS_HR_VERIFICATION": "needs_verification",
    "POSSIBLE_MISMATCH": "possible_mismatch",
}


class LTRError(RuntimeError):
    """Training data or a model artifact failed validation/gates."""


def artifact_sha256(artifact: Mapping[str, Any]) -> str:
    """Hash canonical artifact JSON so approval binds to exact content."""
    canonical = json.dumps(
        artifact, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def extract_ranking_features(
    assessment: Mapping[str, Any],
    criterion_results: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, float]:
    """Features for one assessed application; no identity/demographic data."""
    results = list(criterion_results or [])
    total = len(results)

    def rate(outcome: str) -> float:
        if not total:
            return 0.0
        return sum(1 for item in results if str(item.get("outcome") or "").upper() == outcome) / total

    def decision_rate(source: str) -> float:
        if not total:
            return 0.0
        return sum(1 for item in results if str(item.get("decision_source") or "").upper() == source) / total

    strengths = []
    for item in results:
        try:
            value = float(item.get("evidence_strength"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            strengths.append(min(1.0, max(0.0, value)))

    status = str(assessment.get("matching_status") or "NOT_ASSESSED").upper()
    score = assessment.get("matching_score")
    try:
        score_value = float(score) / 100 if score is not None else 0.0
    except (TypeError, ValueError):
        score_value = 0.0
    try:
        coverage = float(assessment.get("evidence_coverage") or 0)
    except (TypeError, ValueError):
        coverage = 0.0

    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update({
        "matching_score": min(1.0, max(0.0, score_value)),
        "evidence_coverage": min(1.0, max(0.0, coverage)),
        "strong_match_rate": rate("STRONG_MATCH"),
        "match_rate": rate("MATCH"),
        "no_match_rate": rate("NO_MATCH"),
        "unclear_rate": rate("UNCLEAR"),
        "rule_decision_rate": decision_rate("RULE"),
        "llm_decision_rate": decision_rate("LLM"),
        "avg_evidence_strength": sum(strengths) / len(strengths) if strengths else 0.0,
        "mandatory_no_match": 1.0 if any(
            str(item.get("outcome") or "").upper() == "NO_MATCH"
            and str(item.get("category") or "").upper() == "MUST_HAVE"
            for item in results
        ) else 0.0,
    })
    status_feature = STATUS_FEATURES.get(status)
    if status_feature:
        features[status_feature] = 1.0
    return features


def _feature_vector(features: Mapping[str, Any]) -> list[float]:
    vector: list[float] = []
    for name in FEATURE_NAMES:
        try:
            value = float(features.get(name, 0.0))
        except (TypeError, ValueError):
            value = 0.0
        vector.append(value if math.isfinite(value) else 0.0)
    return vector


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1 + exp_value)


def _dcg(labels: list[float], limit: int = 10) -> float:
    return sum(
        (2 ** label - 1) / math.log2(index + 2)
        for index, label in enumerate(labels[:limit])
    )


def ranking_metrics(examples: list[dict[str, Any]], scores: list[float]) -> dict[str, Any]:
    """Pairwise accuracy, NDCG@10 and Kendall-style agreement per group."""
    by_group: dict[str, list[tuple[float, float, str]]] = {}
    for example, score in zip(examples, scores, strict=True):
        by_group.setdefault(example["group_id"], []).append(
            (float(example["label"]), float(score), example["application_id"]))

    pair_total = pair_correct = 0
    ndcg_values: list[float] = []
    for rows in by_group.values():
        for index, (label_a, score_a, _) in enumerate(rows):
            for label_b, score_b, _ in rows[index + 1:]:
                if label_a == label_b:
                    continue
                pair_total += 1
                if (label_a - label_b) * (score_a - score_b) > 0:
                    pair_correct += 1
                elif score_a == score_b:
                    pair_correct += 0.5
        predicted = [label for label, _, _ in sorted(rows, key=lambda row: -row[1])]
        ideal = sorted((label for label, _, _ in rows), reverse=True)
        ideal_dcg = _dcg(ideal)
        if ideal_dcg:
            ndcg_values.append(_dcg(predicted) / ideal_dcg)
    return {
        "pairwise_accuracy": round(pair_correct / pair_total, 6) if pair_total else None,
        "pairwise_pairs": pair_total,
        "ndcg_at_10": round(sum(ndcg_values) / len(ndcg_values), 6) if ndcg_values else None,
        "groups_evaluated": len(ndcg_values),
    }


def _split_groups(examples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Hold out whole groups deterministically (about 20%)."""
    groups = sorted({example["group_id"] for example in examples})
    test_groups = {
        group for group in groups
        if int(hashlib.sha256(group.encode("utf-8")).hexdigest()[:8], 16) % 5 == 0
    }
    if not test_groups or len(test_groups) == len(groups):
        test_groups = {groups[-1]} if len(groups) > 1 else set()
    train = [example for example in examples if example["group_id"] not in test_groups]
    test = [example for example in examples if example["group_id"] in test_groups]
    return train, test


def train_ltr_model(
    raw_examples: Iterable[Mapping[str, Any]],
    *,
    min_examples: int = 30,
    min_groups: int = 5,
    epochs: int = 300,
    learning_rate: float = 0.1,
    l2: float = 0.01,
) -> dict[str, Any]:
    """Train a deterministic pairwise logistic ranker.

    Raises :class:`LTRError` when the labelled data cannot support a
    defensible model; callers must not fall back to an untrained artifact.
    """
    examples: list[dict[str, Any]] = []
    for raw in raw_examples:
        group_id = str(raw.get("group_id") or raw.get("position_id") or "")
        application_id = str(raw.get("application_id") or raw.get("id") or "")
        try:
            label = float(raw.get("label", raw.get("relevance")))
        except (TypeError, ValueError):
            continue
        features = raw.get("features") if isinstance(raw.get("features"), Mapping) else {}
        if group_id and application_id and math.isfinite(label):
            examples.append({
                "group_id": group_id,
                "application_id": application_id,
                "label": label,
                "features": _feature_vector(features),
            })
    examples.sort(key=lambda item: (item["group_id"], item["application_id"]))

    groups = {example["group_id"] for example in examples}
    labels = {example["label"] for example in examples}
    if len(examples) < min_examples:
        raise LTRError(f"LTR cần ít nhất {min_examples} ví dụ có nhãn; hiện có {len(examples)}")
    if len(groups) < min_groups:
        raise LTRError(f"LTR cần ít nhất {min_groups} nhóm/position; hiện có {len(groups)}")
    if len(labels) < 2:
        raise LTRError("LTR cần ít nhất hai mức relevance khác nhau")

    train, test = _split_groups(examples)
    if not train or not test:
        raise LTRError("Không tách được tập train/test theo nhóm")

    means: list[float] = []
    stds: list[float] = []
    for index in range(len(FEATURE_NAMES)):
        values = [example["features"][index] for example in train]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        stds.append(math.sqrt(variance) or 1.0)

    def standardized(example: dict[str, Any]) -> list[float]:
        return [
            (value - means[index]) / stds[index]
            for index, value in enumerate(example["features"])
        ]

    pairs: list[tuple[list[float], float]] = []
    by_group: dict[str, list[dict[str, Any]]] = {}
    for example in train:
        by_group.setdefault(example["group_id"], []).append(example)
    for rows in by_group.values():
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                if first["label"] == second["label"]:
                    continue
                high, low = (first, second) if first["label"] > second["label"] else (second, first)
                diff = [
                    a - b for a, b in zip(standardized(high), standardized(low), strict=True)
                ]
                pairs.append((diff, abs(float(high["label"] - low["label"]))))
    pairs.sort(key=lambda pair: ([round(value, 8) for value in pair[0]], pair[1]))
    if not pairs:
        raise LTRError("Không có cặp so sánh nào trong tập train")

    weights = [0.0] * len(FEATURE_NAMES)
    for _ in range(epochs):
        gradients = [0.0] * len(FEATURE_NAMES)
        total_weight = 0.0
        for diff, weight in pairs:
            probability = _sigmoid(sum(w * d for w, d in zip(weights, diff, strict=True)))
            error = (1 - probability) * weight
            total_weight += weight
            for index, value in enumerate(diff):
                gradients[index] += error * value
        if not total_weight:
            break
        for index in range(len(weights)):
            gradient = gradients[index] / total_weight - l2 * weights[index]
            weights[index] += learning_rate * gradient

    def score(example: dict[str, Any]) -> float:
        return _sigmoid(sum(
            weight * value
            for weight, value in zip(weights, standardized(example), strict=True)
        ))

    train_metrics = ranking_metrics(train, [score(example) for example in train])
    test_metrics = ranking_metrics(test, [score(example) for example in test])
    data_hash = hashlib.sha256(json.dumps(
        examples, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "artifact_type": "pairwise-logistic-ltr",
        "model_version": f"ltr-{data_hash[:12]}",
        "feature_names": list(FEATURE_NAMES),
        "means": means,
        "stds": stds,
        "weights": weights,
        "training": {
            "examples": len(examples),
            "groups": len(groups),
            "train_groups": len({example["group_id"] for example in train}),
            "test_groups": len({example["group_id"] for example in test}),
            "train_examples": len(train),
            "test_examples": len(test),
            "train_pairs": len(pairs),
            "data_sha256": data_hash,
            "label_source": "caller-supplied",
        },
        "metrics": {"train": train_metrics, "test": test_metrics},
    }


class LTRModel:
    """A validated LTR artifact used for shadow or gated active scoring."""

    def __init__(self, artifact: Mapping[str, Any]) -> None:
        if artifact.get("artifact_type") != "pairwise-logistic-ltr":
            raise LTRError("Loại artifact LTR không được hỗ trợ")
        if list(artifact.get("feature_names") or []) != list(FEATURE_NAMES):
            raise LTRError("Feature schema của artifact LTR không khớp")
        self.artifact = dict(artifact)
        self.artifact_sha256 = artifact_sha256(self.artifact)
        self.model_version = str(artifact.get("model_version") or "")
        self.means = [float(value) for value in artifact.get("means") or []]
        self.stds = [float(value) for value in artifact.get("stds") or []]
        self.weights = [float(value) for value in artifact.get("weights") or []]
        if not self.model_version or len(self.means) != len(FEATURE_NAMES) \
                or len(self.stds) != len(FEATURE_NAMES) or len(self.weights) != len(FEATURE_NAMES):
            raise LTRError("Artifact LTR thiếu weights/scaler")
        if (not all(math.isfinite(v) for v in self.means + self.stds + self.weights)
                or any(value <= 0 for value in self.stds)):
            raise LTRError("Artifact LTR chứa weights/scaler không hợp lệ")

    @classmethod
    def from_artifact(cls, artifact: Mapping[str, Any]) -> "LTRModel":
        return cls(artifact)

    @classmethod
    def load(cls, path: str | Path) -> "LTRModel":
        try:
            artifact = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LTRError(f"Không đọc được artifact LTR: {type(exc).__name__}") from None
        if not isinstance(artifact, dict):
            raise LTRError("Artifact LTR phải là JSON object")
        return cls(artifact)

    def passes_gates(
        self,
        *,
        min_ndcg: float,
        min_pairwise: float,
        min_test_examples: int = 0,
        min_test_groups: int = 0,
    ) -> bool:
        metrics = (self.artifact.get("metrics") or {}).get("test") or {}
        training = self.artifact.get("training") or {}
        ndcg = metrics.get("ndcg_at_10")
        pairwise = metrics.get("pairwise_accuracy")
        try:
            test_examples = int(training.get("test_examples") or 0)
        except (TypeError, ValueError):
            test_examples = 0
        try:
            test_groups = int(training.get("test_groups") or metrics.get("groups_evaluated") or 0)
        except (TypeError, ValueError):
            test_groups = 0
        return (
            type(ndcg) in (int, float) and math.isfinite(float(ndcg)) and min_ndcg <= float(ndcg) <= 1
            and type(pairwise) in (int, float) and math.isfinite(float(pairwise)) and min_pairwise <= float(pairwise) <= 1
            and test_examples >= min_test_examples
            and test_groups >= min_test_groups
        )

    def score(self, features: Mapping[str, Any]) -> float:
        values = _feature_vector(features)
        standardized = [
            (value - self.means[index]) / (self.stds[index] or 1.0)
            for index, value in enumerate(values)
        ]
        return round(_sigmoid(sum(
            weight * value for weight, value in zip(self.weights, standardized, strict=True)
        )), 6)
