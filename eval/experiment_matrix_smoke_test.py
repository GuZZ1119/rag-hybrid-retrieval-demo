#!/usr/bin/env python3
"""Smoke test for the static experiment-comparison report."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_experiment_matrix as matrix


def payload(metrics):
    return {"metrics": metrics}


def main() -> None:
    payloads = {
        label: payload({"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0, "precision_at_3": 0.3, "ndcg_at_5": 0.9, "mrr_at_10": 0.9, "negative_no_answer_rate": 0.5, "graph_evidence_coverage": 0.4})
        for label, _, _ in matrix.CONFIGURATIONS
    }
    report = matrix.render_matrix(payloads)
    assert "HYBRID+Graph" in report
    assert "Recall@5" in report


if __name__ == "__main__":
    main()
