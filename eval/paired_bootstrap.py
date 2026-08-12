#!/usr/bin/env python3
"""Estimate paired 95% confidence intervals between two frozen RAG runs."""

import argparse
import json
import random
import sys
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, List, Tuple


DEFAULT_METRICS = ["recall_at_5", "ndcg_at_5", "mrr_at_10"]
COMPARABILITY_FIELDS = (
    "datasetSha256",
    "qrelsSha256",
    "splitManifestSha256",
    "corpusManifestSha256",
    "split",
    "endpoint",
    "topK",
)


def load_payload(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("caseMetrics"), list):
        raise ValueError(f"{path}: expected an evaluation payload with caseMetrics")
    return value


def percentile(values: List[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def case_values(payload: Dict[str, Any], metric: str) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for case in payload["caseMetrics"]:
        case_id = case.get("id")
        value = case.get("values", {}).get(metric)
        if not isinstance(case_id, str):
            raise ValueError("caseMetrics entries need string ids")
        if value is not None:
            if not isinstance(value, (int, float)):
                raise ValueError(f"{case_id}: {metric} must be numeric or null")
            values[case_id] = float(value)
    return values


def compare_metadata(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> List[str]:
    return [field for field in COMPARABILITY_FIELDS if baseline.get(field) != candidate.get(field)]


def paired_bootstrap(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    metric: str,
    samples: int,
    seed: int,
) -> Dict[str, Any]:
    baseline_values = case_values(baseline, metric)
    candidate_values = case_values(candidate, metric)
    paired_ids = sorted(set(baseline_values) & set(candidate_values))
    if not paired_ids:
        raise ValueError(f"{metric}: no paired case values are available")

    differences = [candidate_values[case_id] - baseline_values[case_id] for case_id in paired_ids]
    random_generator = random.Random(seed)
    bootstrap_means = [
        fmean(random_generator.choice(differences) for _ in differences)
        for _ in range(samples)
    ]
    return {
        "metric": metric,
        "pairedCases": len(differences),
        "baselineEligibleCases": len(baseline_values),
        "candidateEligibleCases": len(candidate_values),
        "baselineMean": fmean(baseline_values[case_id] for case_id in paired_ids),
        "candidateMean": fmean(candidate_values[case_id] for case_id in paired_ids),
        "observedDelta": fmean(differences),
        "ci95": [percentile(bootstrap_means, 0.025), percentile(bootstrap_means, 0.975)],
        "probabilityCandidateGreater": sum(value > 0 for value in bootstrap_means) / samples,
        "samples": samples,
        "seed": seed,
    }


def render_report(results: List[Dict[str, Any]], baseline: Path, candidate: Path) -> str:
    lines = [
        "# Paired Bootstrap Comparison",
        "",
        f"- Baseline: `{baseline.name}`",
        f"- Candidate: `{candidate.name}`",
        "- Method: paired non-parametric bootstrap over shared eligible cases; 95% percentile confidence interval for candidate minus baseline. Eligibility counts are reported because answer metrics can be unavailable after a no-answer decision.",
        "",
        "| Metric | Paired / baseline / candidate eligible | Baseline | Candidate | Delta | 95% CI | P(delta > 0) |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for result in results:
        low, high = result["ci95"]
        lines.append(
            f"| {result['metric']} | {result['pairedCases']} / {result['baselineEligibleCases']} / {result['candidateEligibleCases']} | {result['baselineMean']:.3f} | "
            f"{result['candidateMean']:.3f} | {result['observedDelta']:+.3f} | "
            f"[{low:+.3f}, {high:+.3f}] | {result['probabilityCandidateGreater']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paired bootstrap confidence intervals for two RAG evaluation payloads.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS), help="Comma-separated case metrics to compare.")
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    try:
        if args.samples < 100:
            raise ValueError("samples must be at least 100")
        metrics = [metric.strip() for metric in args.metrics.split(",") if metric.strip()]
        if not metrics:
            raise ValueError("at least one metric is required")
        baseline = load_payload(args.baseline)
        candidate = load_payload(args.candidate)
        mismatches = compare_metadata(baseline, candidate)
        if mismatches:
            raise ValueError(f"runs are not comparable: {', '.join(mismatches)}")
        results = [paired_bootstrap(baseline, candidate, metric, args.samples, args.seed) for metric in metrics]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_report(results, args.baseline, args.candidate), encoding="utf-8")
        json_output = args.json_output or args.output.with_suffix(".json")
        json_output.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
        print(args.output.read_text(encoding="utf-8"), end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"paired bootstrap failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
