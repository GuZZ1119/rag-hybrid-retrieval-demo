#!/usr/bin/env python3
"""Fail when a candidate RAG experiment regresses beyond documented tolerances."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_MIN_DELTAS = {
    "recall_at_5": -0.05,
    "precision_at_3": -0.05,
    "ndcg_at_5": -0.05,
    "mrr_at_10": -0.03,
    "negative_no_answer_rate": -0.05,
    "citation_coverage": -0.05,
    "extractive_citation_faithfulness": -0.05,
    "extractive_claim_faithfulness": -0.05,
    "answer_correctness": -0.05,
    "citation_correctness": -0.05,
    "citation_completeness": -0.05,
}


def load_payload(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
        raise ValueError(f"{path}: expected a metrics JSON payload")
    return payload


def compare_metrics(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    min_deltas: Dict[str, float],
) -> List[str]:
    errors = []
    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate["metrics"]
    for field in (
        "datasetSha256",
        "qrelsSha256",
        "splitManifestSha256",
        "corpusManifestSha256",
        "split",
        "mode",
        "endpoint",
        "topK",
        "graphEnabled",
    ):
        if baseline.get(field) != candidate.get(field):
            errors.append(f"{field} differs; experiments are not comparable")

    for metric, min_delta in min_deltas.items():
        if metric not in baseline_metrics or metric not in candidate_metrics:
            continue
        baseline_value = float(baseline_metrics[metric])
        candidate_value = float(candidate_metrics[metric])
        delta = candidate_value - baseline_value
        if delta < min_delta:
            errors.append(
                f"{metric} regressed by {delta:.3f}; allowed minimum delta is {min_delta:.3f}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two RAG experiment metric payloads.")
    parser.add_argument("--baseline", type=Path, required=True, help="Accepted metrics JSON payload.")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate metrics JSON payload.")
    parser.add_argument("--min-recall-at-5-delta", type=float, default=DEFAULT_MIN_DELTAS["recall_at_5"])
    parser.add_argument("--min-precision-at-3-delta", type=float, default=DEFAULT_MIN_DELTAS["precision_at_3"])
    parser.add_argument("--min-ndcg-at-5-delta", type=float, default=DEFAULT_MIN_DELTAS["ndcg_at_5"])
    parser.add_argument("--min-mrr-at-10-delta", type=float, default=DEFAULT_MIN_DELTAS["mrr_at_10"])
    parser.add_argument("--min-negative-no-answer-delta", type=float, default=DEFAULT_MIN_DELTAS["negative_no_answer_rate"])
    parser.add_argument("--min-citation-coverage-delta", type=float, default=DEFAULT_MIN_DELTAS["citation_coverage"])
    parser.add_argument("--min-extractive-citation-faithfulness-delta", type=float, default=DEFAULT_MIN_DELTAS["extractive_citation_faithfulness"])
    parser.add_argument("--min-extractive-claim-faithfulness-delta", type=float, default=DEFAULT_MIN_DELTAS["extractive_claim_faithfulness"])
    parser.add_argument("--min-answer-correctness-delta", type=float, default=DEFAULT_MIN_DELTAS["answer_correctness"])
    parser.add_argument("--min-citation-correctness-delta", type=float, default=DEFAULT_MIN_DELTAS["citation_correctness"])
    parser.add_argument("--min-citation-completeness-delta", type=float, default=DEFAULT_MIN_DELTAS["citation_completeness"])
    args = parser.parse_args()

    try:
        baseline = load_payload(args.baseline)
        candidate = load_payload(args.candidate)
        min_deltas = {
            "recall_at_5": args.min_recall_at_5_delta,
            "precision_at_3": args.min_precision_at_3_delta,
            "ndcg_at_5": args.min_ndcg_at_5_delta,
            "mrr_at_10": args.min_mrr_at_10_delta,
            "negative_no_answer_rate": args.min_negative_no_answer_delta,
            "citation_coverage": args.min_citation_coverage_delta,
            "extractive_citation_faithfulness": args.min_extractive_citation_faithfulness_delta,
            "extractive_claim_faithfulness": args.min_extractive_claim_faithfulness_delta,
            "answer_correctness": args.min_answer_correctness_delta,
            "citation_correctness": args.min_citation_correctness_delta,
            "citation_completeness": args.min_citation_completeness_delta,
        }
        errors = compare_metrics(baseline, candidate, min_deltas)
        if errors:
            print("quality gate failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print("quality gate passed")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"quality gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
