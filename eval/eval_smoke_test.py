#!/usr/bin/env python3
"""Smoke tests for the evaluation dataset and metric helpers without an API."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_retrieval_eval as evaluator


def main() -> None:
    items = evaluator.load_dataset(evaluator.DEFAULT_DATASET)
    corpus = evaluator.load_corpus_manifest(evaluator.DEFAULT_CORPUS_MANIFEST, evaluator.DEFAULT_FIXTURE_DIR)
    splits = evaluator.load_split_manifest(evaluator.DEFAULT_SPLIT_MANIFEST, evaluator.DEFAULT_DATASET, {item["id"] for item in items})
    qrels = evaluator.load_qrels(evaluator.DEFAULT_QRELS, items, corpus)
    assert len(items) == 64
    assert len(splits["dev"]) == 20
    assert len(splits["test"]) == 44
    assert len(evaluator.select_split(items, splits, "test")) == 44
    assert len(qrels) == 46
    assert {item["category"] for item in items} == {"keyword", "paraphrase", "relationship", "negative"}
    assert {item["scenario"] for item in items} == evaluator.SCENARIOS

    positive = next(item for item in items if item["id"] == "incident-p1-escalation")
    relevant_result = {
        "filename": "incident_response_guide.txt",
        "chunkId": "eval-e7d01ea9c08d785b:0",
        "content": "P1 事故应在 15分钟内升级给事故指挥官。",
    }
    assert evaluator.is_relevant(relevant_result, qrels[positive["id"]])
    assert not evaluator.is_relevant({"chunkId": "eval-7483368e35ae8ddb:0"}, qrels[positive["id"]])

    hit_case = evaluator.evaluate_item(positive, {"decision": "ANSWER", "results": [relevant_result]}, top_k=10, qrels=qrels)
    miss_case = evaluator.evaluate_item(items[0], {"decision": "NO_ANSWER", "results": []}, top_k=10, qrels=qrels)
    negative_case = evaluator.evaluate_item(
        next(item for item in items if item["category"] == "negative"),
        {"decision": "NO_ANSWER", "results": []},
        top_k=10, qrels=qrels,
    )
    metrics = evaluator.calculate_metrics([hit_case, miss_case, negative_case])
    assert metrics["recall_at_1"] == 0.5
    assert metrics["recall_at_3"] == 0.5
    assert metrics["recall_at_5"] == 0.5
    assert metrics["precision_at_3"] == 1 / 6
    assert metrics["precision_at_5"] == 0.1
    assert metrics["ndcg_at_3"] == 0.5
    assert metrics["ndcg_at_5"] == 0.5
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["positive_answer_rate"] == 0.5
    assert metrics["negative_no_answer_rate"] == 1.0
    assert metrics["difficulty_metrics"]["standard"]["cases"] == 2

    relationship = next(item for item in items if item["category"] == "relationship")
    relationship_case = evaluator.evaluate_item(
        relationship,
        {
            "decision": "ANSWER",
            "results": [{**relevant_result, "graphRank": 1}],
            "graphEvidence": [{"entity": "采购申请"}],
            "graphRouted": True,
        },
        top_k=10, qrels=qrels,
    )
    graph_metrics = evaluator.calculate_metrics([relationship_case])
    assert graph_metrics["graph_evidence_coverage"] == 1.0
    assert graph_metrics["graph_route_rate"] == 1.0
    assert graph_metrics["graph_candidate_coverage"] == 1.0

    ask_case = evaluator.evaluate_item(
        positive,
        {
            "decision": "ANSWER",
            "results": [relevant_result],
            "answerMode": "EXTRACTIVE",
            "answer": "Evidence from incident_response_guide.txt: P1 事故应在 15分钟内升级给事故指挥官。",
            "citations": [{
                "filename": "incident_response_guide.txt",
                "chunkId": "eval-e7d01ea9c08d785b:0",
                "contentPreview": "P1 事故应在 15分钟内升级给事故指挥官。",
            }],
        },
        top_k=10, qrels=qrels,
    )
    ask_metrics = evaluator.calculate_metrics([ask_case])
    assert ask_metrics["citation_coverage"] == 1.0
    assert ask_metrics["extractive_citation_faithfulness"] == 1.0
    assert ask_metrics["faithfulness_evaluable_cases"] == 1

    llm_case = evaluator.evaluate_item(
        positive,
        {"decision": "ANSWER", "results": [relevant_result], "answerMode": "LLM", "answer": "A paraphrased answer.", "citations": []},
        top_k=10, qrels=qrels,
    )
    assert llm_case["citationFaithfulness"] is None

    report = evaluator.render_report([hit_case, miss_case, negative_case], metrics, "http://example.test", 10, "VECTOR")
    assert "# VECTOR Retrieval Baseline" in report
    assert "Precision@3" in report
    assert "nDCG@5" in report
    assert "Negative no-answer rate" in report

    payload = evaluator.build_metrics_payload(
        metrics,
        evaluator.DEFAULT_DATASET,
        evaluator.DEFAULT_QRELS,
        evaluator.DEFAULT_SPLIT_MANIFEST,
        evaluator.DEFAULT_CORPUS_MANIFEST,
        "test",
        "http://example.test",
        10,
        "HYBRID",
        "search",
        True,
        {"hybridRrfK": 60},
        "test-revision",
    )
    assert payload["graphEnabled"] is True
    assert payload["qrels"] == "qrels.jsonl"
    assert payload["split"] == "test"
    assert payload["runtimeConfig"]["hybridRrfK"] == 60
    assert payload["sourceRevision"] == "test-revision"
    assert len(payload["datasetSha256"]) == 64


if __name__ == "__main__":
    main()
