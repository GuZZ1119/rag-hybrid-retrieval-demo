#!/usr/bin/env python3
"""Smoke tests for the offline quality-gate comparison logic."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_gate


def payload(metrics, dataset_sha="same-dataset", graph_enabled=True):
    return {
        "datasetSha256": dataset_sha,
        "qrelsSha256": "same-qrels",
        "splitManifestSha256": "same-split",
        "corpusManifestSha256": "same-corpus",
        "split": "test",
        "mode": "HYBRID",
        "endpoint": "search",
        "topK": 10,
        "graphEnabled": graph_enabled,
        "metrics": metrics,
    }


def main() -> None:
    baseline = payload({"recall_at_5": 1.0, "precision_at_3": 0.3, "ndcg_at_5": 0.9, "mrr_at_10": 0.9, "negative_no_answer_rate": 0.5, "citation_coverage": 1.0, "extractive_citation_faithfulness": 1.0})
    acceptable = payload({"recall_at_5": 0.96, "precision_at_3": 0.27, "ndcg_at_5": 0.87, "mrr_at_10": 0.88, "negative_no_answer_rate": 0.48, "citation_coverage": 0.96, "extractive_citation_faithfulness": 0.96})
    assert not quality_gate.compare_metrics(baseline, acceptable, quality_gate.DEFAULT_MIN_DELTAS)

    regressed = payload({"recall_at_5": 0.9, "precision_at_3": 0.2, "ndcg_at_5": 0.7, "mrr_at_10": 0.8, "negative_no_answer_rate": 0.3, "citation_coverage": 0.8, "extractive_citation_faithfulness": 0.8})
    errors = quality_gate.compare_metrics(baseline, regressed, quality_gate.DEFAULT_MIN_DELTAS)
    assert any("recall_at_5" in error for error in errors)
    assert any("precision_at_3" in error for error in errors)
    assert any("ndcg_at_5" in error for error in errors)
    assert any("extractive_citation_faithfulness" in error for error in errors)
    assert any("negative_no_answer_rate" in error for error in errors)
    assert quality_gate.compare_metrics(baseline, acceptable, quality_gate.DEFAULT_MIN_DELTAS) == []
    assert quality_gate.compare_metrics(baseline, payload(acceptable["metrics"], "other-dataset"), quality_gate.DEFAULT_MIN_DELTAS)
    assert quality_gate.compare_metrics(baseline, payload(acceptable["metrics"], graph_enabled=False), quality_gate.DEFAULT_MIN_DELTAS)


if __name__ == "__main__":
    main()
