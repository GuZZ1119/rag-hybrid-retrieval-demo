#!/usr/bin/env python3
"""Smoke tests for the evaluation dataset and metric helpers without an API."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_retrieval_eval as evaluator


def main() -> None:
    items = evaluator.load_dataset(evaluator.DEFAULT_DATASET)
    assert len(items) == 12
    assert {item["category"] for item in items} == {"keyword", "paraphrase", "relationship", "negative"}

    positive = next(item for item in items if item["id"] == "incident-p1-escalation")
    relevant_result = {
        "filename": "incident_response_guide.txt",
        "content": "P1 事故应在 15分钟内升级给事故指挥官。",
    }
    assert evaluator.is_relevant(relevant_result, positive)
    assert not evaluator.is_relevant({"filename": "remote_work_policy.txt", "content": relevant_result["content"]}, positive)

    hit_case = evaluator.evaluate_item(positive, [relevant_result], top_k=10)
    miss_case = evaluator.evaluate_item(items[0], [], top_k=10)
    negative_case = evaluator.evaluate_item(next(item for item in items if item["category"] == "negative"), [], top_k=10)
    metrics = evaluator.calculate_metrics([hit_case, miss_case, negative_case])
    assert metrics["recall_at_3"] == 0.5
    assert metrics["recall_at_5"] == 0.5
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["negative_no_result_rate"] == 1.0

    report = evaluator.render_report([hit_case, miss_case, negative_case], metrics, "http://example.test", 10, "VECTOR")
    assert "# VECTOR Retrieval Baseline" in report


if __name__ == "__main__":
    main()
