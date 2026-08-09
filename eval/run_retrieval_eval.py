#!/usr/bin/env python3
"""Run a small, repeatable retrieval evaluation against the demo API."""

import argparse
import json
import mimetypes
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "golden_qa.jsonl"
DEFAULT_FIXTURE_DIR = EVAL_DIR / "fixtures"
DEFAULT_REPORT = EVAL_DIR / "reports" / "latest.md"
POSITIVE_CATEGORIES = {"keyword", "paraphrase", "relationship"}
REQUEST_TIMEOUT_SECONDS = 300


def normalize(value: str) -> str:
    return "".join(value.lower().split())


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON on line {line_number}: {e.msg}") from e
    validate_dataset(items)
    return items


def validate_dataset(items: List[Dict[str, Any]]) -> None:
    if not items:
        raise ValueError("evaluation dataset is empty")

    ids = set()
    for item in items:
        item_id = item.get("id")
        category = item.get("category")
        query = item.get("query")
        expected_file = item.get("expected_file")
        expected_terms = item.get("expected_terms")
        expected_graph_entities = item.get("expected_graph_entities", [])
        difficulty = item.get("difficulty", "standard")

        if not isinstance(item_id, str) or not item_id:
            raise ValueError("every item needs a non-empty string id")
        if item_id in ids:
            raise ValueError(f"duplicate evaluation id: {item_id}")
        ids.add(item_id)
        if category not in POSITIVE_CATEGORIES | {"negative"}:
            raise ValueError(f"{item_id}: unsupported category {category!r}")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{item_id}: query must be a non-empty string")
        if not isinstance(expected_terms, list) or not all(isinstance(term, str) and term for term in expected_terms):
            raise ValueError(f"{item_id}: expected_terms must be a list of non-empty strings")
        if not isinstance(expected_graph_entities, list) or not all(isinstance(entity, str) and entity for entity in expected_graph_entities):
            raise ValueError(f"{item_id}: expected_graph_entities must be a list of non-empty strings")
        if difficulty not in {"standard", "challenge"}:
            raise ValueError(f"{item_id}: difficulty must be standard or challenge")

        if category == "negative":
            if expected_file is not None or expected_terms:
                raise ValueError(f"{item_id}: negative items must not define expected evidence")
        elif not isinstance(expected_file, str) or not expected_file or not expected_terms:
            raise ValueError(f"{item_id}: positive items need expected_file and expected_terms")


def request_json(
    url: str,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API request failed ({e.code}) for {url}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"could not reach API at {url}: {e.reason}") from e


def upload_file(api_url: str, path: Path) -> Dict[str, Any]:
    boundary = f"----rag-eval-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return request_json(
        f"{api_url}/upload",
        method="POST",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def bootstrap_fixtures(api_url: str, items: List[Dict[str, Any]], fixture_dir: Path, mode: str) -> List[str]:
    expected_files = sorted({item["expected_file"] for item in items if item["expected_file"]})
    missing_paths = [fixture_dir / filename for filename in expected_files if not (fixture_dir / filename).is_file()]
    if missing_paths:
        raise RuntimeError(f"fixture files are missing: {', '.join(str(path) for path in missing_paths)}")

    fixture_paths = sorted(path for path in fixture_dir.iterdir() if path.is_file())
    if not fixture_paths:
        raise RuntimeError(f"no fixture files found in {fixture_dir}")

    listed = request_json(f"{api_url}/files")
    existing_filenames = {item.get("filename") for item in listed.get("files", [])}
    uploaded = []
    for path in fixture_paths:
        if path.name not in existing_filenames:
            upload_file(api_url, path)
            uploaded.append(path.name)

    if mode == "TEXT":
        request_json(f"{api_url}/reindex", method="POST")
    else:
        request_json(
            f"{api_url}/index/config",
            method="POST",
            body=json.dumps({"indexMode": mode}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        request_json(f"{api_url}/index/rebuild", method="POST")
    return uploaded


def is_relevant(result: Dict[str, Any], item: Dict[str, Any]) -> bool:
    if item["category"] == "negative":
        return False
    if result.get("filename") != item["expected_file"]:
        return False
    content = normalize(str(result.get("content", "")))
    return all(normalize(term) in content for term in item["expected_terms"])


def evaluate_item(item: Dict[str, Any], response: Dict[str, Any], top_k: int) -> Dict[str, Any]:
    results = response.get("results", [])
    citations = response.get("citations")
    relevant_ranks = [rank for rank, result in enumerate(results[:top_k], start=1) if is_relevant(result, item)]
    return {
        "item": item,
        "decision": response.get("decision", "ANSWER"),
        "decisionReason": response.get("decisionReason"),
        "decisionEvidence": response.get("decisionEvidence", {}),
        "graphEvidence": response.get("graphEvidence", []),
        "graphRouted": bool(response.get("graphRouted")),
        "graphRouteReason": response.get("graphRouteReason"),
        "graphCandidateMatch": any(result.get("graphRank") is not None for result in results[:top_k]),
        "graphEvidenceMatch": any(
            normalize(str(path.get("entity", ""))) in {normalize(entity) for entity in item.get("expected_graph_entities", [])}
            for path in response.get("graphEvidence", [])
        ),
        "citationMatch": None if citations is None else any(
            citation.get("filename") == item.get("expected_file")
            for citation in citations
        ),
        "results": results[:top_k],
        "firstRelevantRank": relevant_ranks[0] if relevant_ranks else None,
        "relevantCount": len(relevant_ranks),
    }


def calculate_metrics(cases: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    cases = list(cases)
    positive_cases = [case for case in cases if case["item"]["category"] != "negative"]
    negative_cases = [case for case in cases if case["item"]["category"] == "negative"]
    relationship_cases = [case for case in cases if case["item"]["category"] == "relationship"]
    citation_cases = [
        case for case in positive_cases
        if case["citationMatch"] is not None
    ]
    if not positive_cases:
        raise ValueError("evaluation dataset has no positive cases")

    positive_count = len(positive_cases)
    metrics: Dict[str, Any] = {
        "positive_cases": positive_count,
        "negative_cases": len(negative_cases),
        "recall_at_3": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 3 for case in positive_cases) / positive_count,
        "recall_at_5": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 5 for case in positive_cases) / positive_count,
        "mrr_at_10": sum(1 / case["firstRelevantRank"] if case["firstRelevantRank"] else 0 for case in positive_cases) / positive_count,
        "positive_answer_rate": sum(case["decision"] == "ANSWER" for case in positive_cases) / positive_count,
    }
    if negative_cases:
        metrics["negative_no_answer_rate"] = sum(case["decision"] == "NO_ANSWER" for case in negative_cases) / len(negative_cases)
    if relationship_cases:
        metrics["graph_evidence_coverage"] = sum(case["graphEvidenceMatch"] for case in relationship_cases) / len(relationship_cases)
        metrics["graph_route_rate"] = sum(case["graphRouted"] for case in relationship_cases) / len(relationship_cases)
        metrics["graph_candidate_coverage"] = sum(case["graphCandidateMatch"] for case in relationship_cases) / len(relationship_cases)
    if citation_cases:
        metrics["citation_coverage"] = sum(case["citationMatch"] for case in citation_cases) / len(citation_cases)
    difficulty_metrics = {}
    for difficulty in sorted({case["item"].get("difficulty", "standard") for case in positive_cases}):
        difficulty_cases = [case for case in positive_cases if case["item"].get("difficulty", "standard") == difficulty]
        difficulty_metrics[difficulty] = {
            "cases": len(difficulty_cases),
            "recall_at_3": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 3 for case in difficulty_cases) / len(difficulty_cases),
            "mrr_at_10": sum(1 / case["firstRelevantRank"] if case["firstRelevantRank"] else 0 for case in difficulty_cases) / len(difficulty_cases),
        }
    metrics["difficulty_metrics"] = difficulty_metrics
    return metrics


def format_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_report(cases: List[Dict[str, Any]], metrics: Dict[str, Any], api_url: str, top_k: int, mode: str, endpoint: str = "search") -> str:
    category_counts = Counter(case["item"]["category"] for case in cases)
    report_name = "BM25" if mode == "TEXT" else mode
    if endpoint == "ask":
        report_name = f"{report_name} Ask"
    lines = [
        f"# {report_name} Retrieval Baseline",
        "",
        f"This report is generated by `eval/run_retrieval_eval.py` against the current `/{endpoint}` endpoint.",
        "",
        f"- API: `{api_url}`",
        f"- Search mode: `{mode}`",
        f"- Candidate depth: `{top_k}`",
        f"- Dataset: `{len(cases)}` cases ({', '.join(f'{name}: {count}' for name, count in sorted(category_counts.items()))})",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Recall@3 | {format_rate(metrics['recall_at_3'])} |",
        f"| Recall@5 | {format_rate(metrics['recall_at_5'])} |",
        f"| MRR@10 | {metrics['mrr_at_10']:.3f} |",
        f"| Positive answer rate | {format_rate(metrics['positive_answer_rate'])} |",
    ]
    if "negative_no_answer_rate" in metrics:
        lines.append(f"| Negative no-answer rate | {format_rate(metrics['negative_no_answer_rate'])} |")
    if "graph_evidence_coverage" in metrics:
        lines.append(f"| Graph evidence coverage | {format_rate(metrics['graph_evidence_coverage'])} |")
        lines.append(f"| Graph route rate (relationship) | {format_rate(metrics['graph_route_rate'])} |")
        lines.append(f"| Graph candidate coverage (relationship) | {format_rate(metrics['graph_candidate_coverage'])} |")
    if "citation_coverage" in metrics:
        lines.append(f"| Citation coverage | {format_rate(metrics['citation_coverage'])} |")

    lines.extend(["", "## Retrieval by Difficulty", "", "| Difficulty | Cases | Recall@3 | MRR@10 |", "| --- | ---: | ---: | ---: |"])
    for difficulty, values in metrics.get("difficulty_metrics", {}).items():
        lines.append(
            f"| {difficulty} | {values['cases']} | {format_rate(values['recall_at_3'])} | {values['mrr_at_10']:.3f} |"
        )

    failed_cases = [case for case in cases if case["item"]["category"] != "negative" and case["firstRelevantRank"] is None]
    lines.extend(["", "## Failed Retrievals", ""])
    if not failed_cases:
        lines.append("No positive cases missed at the configured candidate depth.")
    else:
        for case in failed_cases:
            item = case["item"]
            lines.extend([
                f"### {item['id']}",
                "",
                f"- Query: {item['query']}",
                f"- Expected evidence: `{item['expected_file']}` containing `{', '.join(item['expected_terms'])}`",
                "- Returned chunks:",
            ])
            if case["results"]:
                for result in case["results"]:
                    lines.append(f"  - #{result.get('rank')} `{result.get('filename')}` / `{result.get('chunkId')}`: {result.get('contentPreview', '')}")
            else:
                lines.append("  - No chunks returned")
            lines.append("")

    decision_errors = [
        case for case in cases
        if (case["item"]["category"] == "negative" and case["decision"] != "NO_ANSWER")
        or (case["item"]["category"] != "negative" and case["decision"] != "ANSWER")
    ]
    lines.extend(["", "## Decision Errors", ""])
    if not decision_errors:
        lines.append("No answer decisions disagreed with the golden labels.")
    else:
        for case in decision_errors:
            item = case["item"]
            lines.append(
                f"- `{item['id']}` ({item['category']}): `{case['decision']}` / "
                f"`{case.get('decisionReason') or 'no reason returned'}`"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    global REQUEST_TIMEOUT_SECONDS
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality for the demo API.")
    parser.add_argument("--api-url", default="http://localhost:8080", help="Demo API base URL.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Golden JSONL dataset path.")
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR, help="Fixture documents directory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT, help="Markdown report output path.")
    parser.add_argument("--top-k", type=int, default=10, choices=range(1, 51), metavar="1..50", help="Search candidate depth.")
    parser.add_argument("--mode", choices=["TEXT", "VECTOR", "HYBRID"], default="TEXT", help="Retrieval path to evaluate.")
    parser.add_argument("--endpoint", choices=["search", "ask"], default="search", help="API endpoint to evaluate.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=300,
        help="Maximum seconds to wait for one API request; vector model loading can take longer on first use.",
    )
    parser.add_argument("--bootstrap", action="store_true", help="Upload missing fixture files and rebuild the index first.")
    parser.add_argument("--validate-only", action="store_true", help="Validate the JSONL dataset without calling the API.")
    args = parser.parse_args()

    try:
        if args.request_timeout <= 0:
            raise ValueError("request timeout must be greater than 0")
        if args.endpoint == "ask" and args.mode != "HYBRID":
            raise ValueError("the ask endpoint only supports HYBRID mode")
        REQUEST_TIMEOUT_SECONDS = args.request_timeout
        items = load_dataset(args.dataset)
        if args.validate_only:
            print(f"evaluation dataset is valid: {len(items)} cases")
            return 0

        api_url = args.api_url.rstrip("/")
        if args.bootstrap:
            uploaded = bootstrap_fixtures(api_url, items, args.fixture_dir, args.mode)
            print(f"fixture bootstrap complete; uploaded {len(uploaded)} file(s)")

        cases = []
        for item in items:
            if args.endpoint == "search":
                query = urlencode({"q": item["query"], "topK": args.top_k, "mode": args.mode})
                response = request_json(f"{api_url}/search?{query}")
            else:
                response = request_json(
                    f"{api_url}/ask",
                    method="POST",
                    body=json.dumps({"q": item["query"], "topK": args.top_k}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            cases.append(evaluate_item(item, response, args.top_k))

        metrics = calculate_metrics(cases)
        report = render_report(cases, metrics, api_url, args.top_k, args.mode, args.endpoint)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(report)
        print(f"report written to {args.output}")
        return 0
    except (OSError, RuntimeError, ValueError) as e:
        print(f"retrieval evaluation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
