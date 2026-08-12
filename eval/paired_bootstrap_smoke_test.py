#!/usr/bin/env python3
"""Smoke test paired bootstrap calculations without a running API."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_bootstrap


def payload(values):
    return {
        "datasetSha256": "dataset",
        "qrelsSha256": "qrels",
        "splitManifestSha256": "split",
        "corpusManifestSha256": "corpus",
        "split": "test",
        "endpoint": "search",
        "topK": 10,
        "caseMetrics": [
            {"id": f"case-{index}", "values": {"ndcg_at_5": value}}
            for index, value in enumerate(values, start=1)
        ],
    }


def main() -> None:
    baseline = payload([0.2, 0.4, 0.6, 0.8])
    candidate = payload([0.3, 0.5, 0.7, 0.9])
    result = paired_bootstrap.paired_bootstrap(baseline, candidate, "ndcg_at_5", samples=200, seed=3)
    assert result["pairedCases"] == 4
    assert result["baselineEligibleCases"] == 4
    assert result["candidateEligibleCases"] == 4
    assert abs(result["observedDelta"] - 0.1) < 1e-12
    assert all(abs(value - 0.1) < 1e-12 for value in result["ci95"])
    assert paired_bootstrap.compare_metadata(baseline, candidate) == []
    candidate["caseMetrics"].pop()
    partial = paired_bootstrap.paired_bootstrap(baseline, candidate, "ndcg_at_5", samples=200, seed=3)
    assert partial["pairedCases"] == 3
    assert partial["baselineEligibleCases"] == 4
    assert partial["candidateEligibleCases"] == 3
    candidate["split"] = "dev"
    assert "split" in paired_bootstrap.compare_metadata(baseline, candidate)


if __name__ == "__main__":
    main()
