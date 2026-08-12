#!/usr/bin/env python3
"""Run a small, repeatable retrieval evaluation against the demo API."""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import uuid
from collections import Counter
from math import log2
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "golden_qa.jsonl"
DEFAULT_FIXTURE_DIR = EVAL_DIR / "fixtures"
DEFAULT_QRELS = EVAL_DIR / "qrels.jsonl"
DEFAULT_SPLIT_MANIFEST = EVAL_DIR / "split_manifest.json"
DEFAULT_CORPUS_MANIFEST = EVAL_DIR / "corpus_manifest.json"
DEFAULT_REPORT = EVAL_DIR / "reports" / "latest.md"
POSITIVE_CATEGORIES = {"keyword", "paraphrase", "relationship"}
SCENARIOS = {"baseline", "cross_document", "distractor", "multi_condition", "negative", "semantic", "version_conflict"}
REQUEST_TIMEOUT_SECONDS = 300


def normalize(value: str) -> str:
    return "".join(value.lower().split())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        scenario = item.get("scenario")

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
        if scenario not in SCENARIOS:
            raise ValueError(f"{item_id}: scenario must be one of {', '.join(sorted(SCENARIOS))}")

        if category == "negative":
            if expected_file is not None or expected_terms:
                raise ValueError(f"{item_id}: negative items must not define expected evidence")
        elif not isinstance(expected_file, str) or not expected_file or not expected_terms:
            raise ValueError(f"{item_id}: positive items need expected_file and expected_terms")


def load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid {label} JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: {label} must be a JSON object")
    return value


def load_split_manifest(path: Path, dataset_path: Path, item_ids: set[str]) -> Dict[str, List[str]]:
    manifest = load_json_object(path, "split manifest")
    if manifest.get("schemaVersion") != 1:
        raise ValueError(f"{path}: unsupported split manifest schema")
    if manifest.get("datasetSha256") != sha256_file(dataset_path):
        raise ValueError(f"{path}: dataset SHA does not match {dataset_path.name}")
    splits = manifest.get("splits")
    if not isinstance(splits, dict) or set(splits) != {"dev", "test"}:
        raise ValueError(f"{path}: splits must define exactly dev and test")

    seen = set()
    parsed: Dict[str, List[str]] = {}
    for name in ("dev", "test"):
        ids = splits[name]
        if not isinstance(ids, list) or not ids or not all(isinstance(item_id, str) for item_id in ids):
            raise ValueError(f"{path}: {name} split must contain non-empty string ids")
        if len(ids) != len(set(ids)):
            raise ValueError(f"{path}: {name} split contains duplicate ids")
        unknown = set(ids) - item_ids
        if unknown:
            raise ValueError(f"{path}: {name} split contains unknown ids: {', '.join(sorted(unknown))}")
        overlap = seen & set(ids)
        if overlap:
            raise ValueError(f"{path}: splits overlap: {', '.join(sorted(overlap))}")
        seen.update(ids)
        parsed[name] = ids
    if seen != item_ids:
        raise ValueError(f"{path}: splits must cover every dataset item exactly once")
    return parsed


def select_split(items: List[Dict[str, Any]], splits: Dict[str, List[str]], split: str) -> List[Dict[str, Any]]:
    if split == "all":
        return items
    by_id = {item["id"]: item for item in items}
    return [by_id[item_id] for item_id in splits[split]]


def load_corpus_manifest(path: Path, fixture_dir: Path) -> Dict[str, Dict[str, str]]:
    manifest = load_json_object(path, "corpus manifest")
    if manifest.get("schemaVersion") != 1:
        raise ValueError(f"{path}: unsupported corpus manifest schema")
    chunking = manifest.get("chunking")
    if not isinstance(chunking, dict) or chunking.get("chunkSize") != 400 or chunking.get("chunkOverlap") != 120:
        raise ValueError(f"{path}: corpus manifest must freeze chunkSize=400 and chunkOverlap=120")
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError(f"{path}: corpus manifest needs fixtures")

    parsed: Dict[str, Dict[str, str]] = {}
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ValueError(f"{path}: every fixture must be an object")
        filename = fixture.get("filename")
        file_id = fixture.get("fileId")
        digest = fixture.get("sha256")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError(f"{path}: fixture filename is invalid")
        if not isinstance(file_id, str) or not re_fullmatch_file_id(file_id):
            raise ValueError(f"{path}: fixture {filename} has an invalid fileId")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{path}: fixture {filename} has an invalid SHA")
        if filename in parsed:
            raise ValueError(f"{path}: duplicate fixture {filename}")
        fixture_path = fixture_dir / filename
        if not fixture_path.is_file():
            raise ValueError(f"{path}: missing fixture {fixture_path}")
        if sha256_file(fixture_path) != digest:
            raise ValueError(f"{path}: fixture SHA changed for {filename}")
        parsed[filename] = {"fileId": file_id, "sha256": digest}

    actual_filenames = {path.name for path in fixture_dir.iterdir() if path.is_file()}
    if actual_filenames != set(parsed):
        raise ValueError(f"{path}: manifest and fixture directory differ")
    return parsed


def re_fullmatch_file_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value))


def load_qrels(path: Path, items: List[Dict[str, Any]], corpus: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    qrels: Dict[str, Dict[str, int]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}: invalid JSON on line {line_number}: {error.msg}") from error
        query_id = record.get("query_id")
        relevant = record.get("relevant")
        if not isinstance(query_id, str) or not query_id or query_id in qrels:
            raise ValueError(f"{path}: line {line_number} has an invalid or duplicate query_id")
        if not isinstance(relevant, list) or not relevant:
            raise ValueError(f"{path}: {query_id} needs at least one relevant chunk")
        grades: Dict[str, int] = {}
        for evidence in relevant:
            chunk_id = evidence.get("chunk_id") if isinstance(evidence, dict) else None
            grade = evidence.get("grade") if isinstance(evidence, dict) else None
            if not isinstance(chunk_id, str) or not chunk_id or not isinstance(grade, int) or not 1 <= grade <= 3:
                raise ValueError(f"{path}: {query_id} has invalid relevance evidence")
            if chunk_id in grades:
                raise ValueError(f"{path}: {query_id} has duplicate chunk_id {chunk_id}")
            grades[chunk_id] = grade
        qrels[query_id] = grades

    positives = {item["id"] for item in items if item["category"] != "negative"}
    negatives = {item["id"] for item in items if item["category"] == "negative"}
    if set(qrels) != positives:
        missing = positives - set(qrels)
        extra = set(qrels) - positives
        raise ValueError(f"{path}: qrels must match positive cases; missing={sorted(missing)}, extra={sorted(extra)}")
    if negatives & set(qrels):
        raise ValueError(f"{path}: negative cases must not have qrels")

    expected_prefixes = {metadata["fileId"] for metadata in corpus.values()}
    items_by_id = {item["id"]: item for item in items}
    for query_id, grades in qrels.items():
        if any(chunk_id.split(":", 1)[0] not in expected_prefixes for chunk_id in grades):
            raise ValueError(f"{path}: {query_id} references a chunk outside the frozen corpus")
        expected_file_id = corpus[items_by_id[query_id]["expected_file"]]["fileId"]
        if not any(chunk_id.split(":", 1)[0] == expected_file_id for chunk_id in grades):
            raise ValueError(f"{path}: {query_id} qrels must include the labelled primary source file")
    return qrels


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


def upload_file(api_url: str, path: Path, file_id: str) -> Dict[str, Any]:
    boundary = f"----rag-eval-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="fileId"\r\n\r\n',
        f"{file_id}\r\n".encode(),
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


def bootstrap_fixtures(api_url: str, fixture_dir: Path, corpus: Dict[str, Dict[str, str]], mode: str) -> List[str]:
    listed = request_json(f"{api_url}/files")
    existing_pairs = {
        (item.get("fileId"), item.get("filename"))
        for item in listed.get("files", [])
    }
    expected_pairs = {
        (metadata["fileId"], filename)
        for filename, metadata in corpus.items()
    }
    unexpected_pairs = existing_pairs - expected_pairs
    if unexpected_pairs:
        formatted = ", ".join(f"{file_id}:{filename}" for file_id, filename in sorted(unexpected_pairs))
        raise RuntimeError(f"evaluation API is not isolated; unexpected uploaded files: {formatted}")

    uploaded = []
    for filename, metadata in sorted(corpus.items()):
        pair = (metadata["fileId"], filename)
        if pair not in existing_pairs:
            response = upload_file(api_url, fixture_dir / filename, metadata["fileId"])
            if response.get("fileId") != metadata["fileId"] or response.get("filename") != filename:
                raise RuntimeError(f"evaluation upload did not preserve frozen identity for {filename}")
            uploaded.append(filename)

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


def is_relevant(result: Dict[str, Any], qrel_grades: Dict[str, int]) -> bool:
    return result.get("chunkId") in qrel_grades


def relevance_grade(result: Dict[str, Any], qrel_grades: Dict[str, int]) -> int:
    """Return the explicit graded relevance label for a retrieved chunk.

    Qrels are frozen to chunk IDs, so changing extraction logic or chunking
    cannot silently redefine a correct retrieval result.
    """
    return qrel_grades.get(str(result.get("chunkId")), 0)


def reference_claims(item: Dict[str, Any], qrel_grades: Dict[str, int]) -> List[Dict[str, Any]]:
    """Return atomic answer labels, defaulting legacy cases to their primary evidence terms."""
    raw_claims = item.get("reference_claims")
    if raw_claims is None:
        raw_claims = [{
            "id": "primary",
            "required_terms": item["expected_terms"],
            "supporting_chunk_ids": sorted(qrel_grades),
        }]
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError(f"{item['id']}: reference_claims must be a non-empty list")

    claims = []
    seen_ids = set()
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            raise ValueError(f"{item['id']}: reference claim must be an object")
        claim_id = raw_claim.get("id")
        terms = raw_claim.get("required_terms")
        supporting_chunk_ids = raw_claim.get("supporting_chunk_ids")
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen_ids:
            raise ValueError(f"{item['id']}: reference claim id is invalid or duplicated")
        if not isinstance(terms, list) or not terms or not all(isinstance(term, str) and term for term in terms):
            raise ValueError(f"{item['id']}: reference claim {claim_id} needs required_terms")
        if not isinstance(supporting_chunk_ids, list) or not supporting_chunk_ids or not all(isinstance(chunk_id, str) for chunk_id in supporting_chunk_ids):
            raise ValueError(f"{item['id']}: reference claim {claim_id} needs supporting_chunk_ids")
        if not set(supporting_chunk_ids) <= set(qrel_grades):
            raise ValueError(f"{item['id']}: reference claim {claim_id} cites chunks outside qrels")
        seen_ids.add(claim_id)
        claims.append({
            "id": claim_id,
            "requiredTerms": terms,
            "supportingChunkIds": supporting_chunk_ids,
        })
    return claims


def citation_faithfulness(response: Dict[str, Any]) -> Optional[bool]:
    """Check whether the extractive fallback quotes a cited source preview.

    This is intentionally not an LLM-as-judge score: an LLM answer is skipped
    because semantic faithfulness needs a dedicated judge or human review.
    """
    if response.get("answerMode") != "EXTRACTIVE":
        return None
    answer = normalize(str(response.get("answer", "")))
    citations = response.get("citations")
    if not answer or not isinstance(citations, list) or not citations:
        return False
    return any(
        normalize(str(citation.get("contentPreview", ""))) in answer
        for citation in citations
        if citation.get("contentPreview")
    )


def extractive_claim_support(response: Dict[str, Any]) -> Optional[List[bool]]:
    """Evaluate each extractive answer clause against the returned citation previews."""
    if response.get("answerMode") != "EXTRACTIVE":
        return None
    answer = str(response.get("answer", ""))
    if ":" in answer:
        answer = answer.split(":", 1)[1]
    evidence_blocks = [
        re.sub(r"^\[\d+\]\s*", "", block.strip())
        for block in re.split(r"(?=\[\d+\]\s*)", answer)
        if block.strip()
    ]
    claims = [
        segment.strip()
        for block in evidence_blocks
        for segment in re.split(r"[。！？!?]+", block)
        if len(normalize(segment)) >= 4
    ]
    citations = response.get("citations")
    previews = [normalize(str(citation.get("contentPreview", ""))) for citation in citations or []]
    if not claims or not previews:
        return [False]
    return [
        any(normalize(claim) in preview or preview in normalize(claim) for preview in previews if preview)
        for claim in claims
    ]


def evaluate_item(item: Dict[str, Any], response: Dict[str, Any], top_k: int, qrels: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    results = response.get("results", [])
    citations = response.get("citations")
    qrel_grades = qrels.get(item["id"], {})
    claims = [] if item["category"] == "negative" else reference_claims(item, qrel_grades)
    cited_chunk_ids = {
        citation.get("chunkId")
        for citation in citations or []
        if citation.get("chunkId")
    }
    support_chunk_ids = {
        chunk_id
        for claim in claims
        for chunk_id in claim["supportingChunkIds"]
    }
    has_answer = isinstance(response.get("answer"), str)
    normalized_answer = normalize(str(response.get("answer", "")))
    claim_correctness = [
        all(normalize(term) in normalized_answer for term in claim["requiredTerms"])
        for claim in claims
    ]
    citation_completeness = [
        set(claim["supportingChunkIds"]) <= cited_chunk_ids
        for claim in claims
    ]
    relevance_grades = [relevance_grade(result, qrel_grades) for result in results[:top_k]]
    relevant_ranks = [rank for rank, grade in enumerate(relevance_grades, start=1) if grade > 0]
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
        "citationMatch": None if citations is None else any(citation.get("chunkId") in qrel_grades for citation in citations),
        "citationFaithfulness": citation_faithfulness(response),
        "claimFaithfulness": extractive_claim_support(response),
        "referenceClaims": claims,
        "answerCorrectness": None if not claims or not has_answer else sum(claim_correctness) / len(claim_correctness),
        "citationCorrectness": None if citations is None or not citations else sum(chunk_id in support_chunk_ids for chunk_id in cited_chunk_ids) / len(cited_chunk_ids),
        "citationCompleteness": None if citations is None or not claims else sum(citation_completeness) / len(citation_completeness),
        "results": results[:top_k],
        "qrelGrades": qrel_grades,
        "relevanceGrades": relevance_grades,
        "firstRelevantRank": relevant_ranks[0] if relevant_ranks else None,
        "relevantCount": len(relevant_ranks),
    }


def precision_at_k(case: Dict[str, Any], k: int) -> float:
    grades = case["relevanceGrades"][:k]
    return sum(grade > 0 for grade in grades) / k


def ndcg_at_k(case: Dict[str, Any], k: int) -> float:
    grades = case["relevanceGrades"][:k]
    dcg = sum((2**grade - 1) / log2(rank + 1) for rank, grade in enumerate(grades, start=1))
    ideal_grades = sorted(case["qrelGrades"].values(), reverse=True)[:k]
    ideal_dcg = sum((2**grade - 1) / log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def case_metric_values(case: Dict[str, Any]) -> Dict[str, Optional[float]]:
    item = case["item"]
    if item["category"] == "negative":
        return {"negative_no_answer_rate": float(case["decision"] == "NO_ANSWER")}
    claim_faithfulness = case["claimFaithfulness"]
    return {
        "recall_at_1": float(case["firstRelevantRank"] == 1),
        "recall_at_3": float(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 3),
        "recall_at_5": float(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 5),
        "precision_at_3": precision_at_k(case, 3),
        "precision_at_5": precision_at_k(case, 5),
        "ndcg_at_3": ndcg_at_k(case, 3),
        "ndcg_at_5": ndcg_at_k(case, 5),
        "mrr_at_10": 1 / case["firstRelevantRank"] if case["firstRelevantRank"] else 0.0,
        "positive_answer_rate": float(case["decision"] == "ANSWER"),
        "citation_coverage": None if case["citationMatch"] is None else float(case["citationMatch"]),
        "citation_correctness": case["citationCorrectness"],
        "citation_completeness": case["citationCompleteness"],
        "answer_correctness": case["answerCorrectness"],
        "extractive_claim_faithfulness": None if claim_faithfulness is None else sum(claim_faithfulness) / len(claim_faithfulness),
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
    faithfulness_cases = [
        case for case in positive_cases
        if case["citationFaithfulness"] is not None
    ]
    claim_faithfulness_cases = [case for case in positive_cases if case["claimFaithfulness"] is not None]
    answer_cases = [case for case in positive_cases if case["answerCorrectness"] is not None]
    citation_correctness_cases = [case for case in positive_cases if case["citationCorrectness"] is not None]
    citation_completeness_cases = [case for case in positive_cases if case["citationCompleteness"] is not None]
    if not positive_cases:
        raise ValueError("evaluation dataset has no positive cases")

    positive_count = len(positive_cases)
    metrics: Dict[str, Any] = {
        "positive_cases": positive_count,
        "negative_cases": len(negative_cases),
        "recall_at_1": sum(case["firstRelevantRank"] == 1 for case in positive_cases) / positive_count,
        "recall_at_3": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 3 for case in positive_cases) / positive_count,
        "recall_at_5": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 5 for case in positive_cases) / positive_count,
        "precision_at_3": sum(precision_at_k(case, 3) for case in positive_cases) / positive_count,
        "precision_at_5": sum(precision_at_k(case, 5) for case in positive_cases) / positive_count,
        "ndcg_at_3": sum(ndcg_at_k(case, 3) for case in positive_cases) / positive_count,
        "ndcg_at_5": sum(ndcg_at_k(case, 5) for case in positive_cases) / positive_count,
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
    if faithfulness_cases:
        metrics["extractive_citation_faithfulness"] = sum(case["citationFaithfulness"] for case in faithfulness_cases) / len(faithfulness_cases)
        metrics["faithfulness_evaluable_cases"] = len(faithfulness_cases)
    if claim_faithfulness_cases:
        claim_values = [value for case in claim_faithfulness_cases for value in case["claimFaithfulness"]]
        metrics["extractive_claim_faithfulness"] = sum(claim_values) / len(claim_values)
        metrics["claim_faithfulness_evaluable_claims"] = len(claim_values)
    if answer_cases:
        metrics["answer_correctness"] = sum(case["answerCorrectness"] for case in answer_cases) / len(answer_cases)
    if citation_correctness_cases:
        metrics["citation_correctness"] = sum(case["citationCorrectness"] for case in citation_correctness_cases) / len(citation_correctness_cases)
    if citation_completeness_cases:
        metrics["citation_completeness"] = sum(case["citationCompleteness"] for case in citation_completeness_cases) / len(citation_completeness_cases)
    difficulty_metrics = {}
    for difficulty in sorted({case["item"].get("difficulty", "standard") for case in positive_cases}):
        difficulty_cases = [case for case in positive_cases if case["item"].get("difficulty", "standard") == difficulty]
        difficulty_metrics[difficulty] = {
            "cases": len(difficulty_cases),
            "recall_at_1": sum(case["firstRelevantRank"] == 1 for case in difficulty_cases) / len(difficulty_cases),
            "recall_at_3": sum(case["firstRelevantRank"] is not None and case["firstRelevantRank"] <= 3 for case in difficulty_cases) / len(difficulty_cases),
            "precision_at_3": sum(precision_at_k(case, 3) for case in difficulty_cases) / len(difficulty_cases),
            "ndcg_at_5": sum(ndcg_at_k(case, 5) for case in difficulty_cases) / len(difficulty_cases),
            "mrr_at_10": sum(1 / case["firstRelevantRank"] if case["firstRelevantRank"] else 0 for case in difficulty_cases) / len(difficulty_cases),
        }
    metrics["difficulty_metrics"] = difficulty_metrics
    return metrics


def format_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_metrics_payload(
    metrics: Dict[str, Any],
    cases: List[Dict[str, Any]],
    dataset_path: Path,
    qrels_path: Path,
    split_manifest_path: Path,
    corpus_manifest_path: Path,
    split: str,
    api_url: str,
    top_k: int,
    mode: str,
    endpoint: str,
    graph_enabled: bool,
    runtime_config: Dict[str, Any],
    source_revision: str,
) -> Dict[str, Any]:
    return {
        "dataset": dataset_path.name,
        "datasetSha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "qrels": qrels_path.name,
        "qrelsSha256": sha256_file(qrels_path),
        "splitManifest": split_manifest_path.name,
        "splitManifestSha256": sha256_file(split_manifest_path),
        "corpusManifest": corpus_manifest_path.name,
        "corpusManifestSha256": sha256_file(corpus_manifest_path),
        "split": split,
        "apiUrl": api_url,
        "mode": mode,
        "endpoint": endpoint,
        "topK": top_k,
        "graphEnabled": graph_enabled,
        "sourceRevision": source_revision,
        "runtimeConfig": runtime_config,
        "metrics": metrics,
        "caseMetrics": [
            {
                "id": case["item"]["id"],
                "category": case["item"]["category"],
                "values": case_metric_values(case),
            }
            for case in cases
        ],
    }


def render_report(cases: List[Dict[str, Any]], metrics: Dict[str, Any], api_url: str, top_k: int, mode: str, endpoint: str = "search", graph_enabled: bool = True, split: str = "test") -> str:
    category_counts = Counter(case["item"]["category"] for case in cases)
    scenario_counts = Counter(case["item"]["scenario"] for case in cases)
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
        f"- Graph expansion: `{'enabled' if graph_enabled and mode == 'HYBRID' else 'disabled'}`",
        f"- Candidate depth: `{top_k}`",
        f"- Evaluation split: `{split}`",
        f"- Dataset: `{len(cases)}` cases ({', '.join(f'{name}: {count}' for name, count in sorted(category_counts.items()))})",
        f"- Scenarios: {', '.join(f'{name}: {count}' for name, count in sorted(scenario_counts.items()))}",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Recall@1 | {format_rate(metrics['recall_at_1'])} |",
        f"| Recall@3 | {format_rate(metrics['recall_at_3'])} |",
        f"| Recall@5 | {format_rate(metrics['recall_at_5'])} |",
        f"| Precision@3 (one-label) | {format_rate(metrics['precision_at_3'])} |",
        f"| Precision@5 (one-label) | {format_rate(metrics['precision_at_5'])} |",
        f"| nDCG@3 | {metrics['ndcg_at_3']:.3f} |",
        f"| nDCG@5 | {metrics['ndcg_at_5']:.3f} |",
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
    if "extractive_citation_faithfulness" in metrics:
        lines.append(f"| Extractive citation faithfulness | {format_rate(metrics['extractive_citation_faithfulness'])} |")
        lines.append(f"| Faithfulness evaluable cases | {metrics['faithfulness_evaluable_cases']} |")
    if "extractive_claim_faithfulness" in metrics:
        lines.append(f"| Extractive claim faithfulness | {format_rate(metrics['extractive_claim_faithfulness'])} |")
        lines.append(f"| Claim faithfulness evaluable claims | {metrics['claim_faithfulness_evaluable_claims']} |")
    if "answer_correctness" in metrics:
        lines.append(f"| Answer correctness (reference claims) | {format_rate(metrics['answer_correctness'])} |")
    if "citation_correctness" in metrics:
        lines.append(f"| Citation correctness | {format_rate(metrics['citation_correctness'])} |")
    if "citation_completeness" in metrics:
        lines.append(f"| Citation completeness | {format_rate(metrics['citation_completeness'])} |")

    lines.extend(["", "## Retrieval by Difficulty", "", "| Difficulty | Cases | Recall@1 | Recall@3 | Precision@3 | nDCG@5 | MRR@10 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for difficulty, values in metrics.get("difficulty_metrics", {}).items():
        lines.append(
            f"| {difficulty} | {values['cases']} | {format_rate(values['recall_at_1'])} | {format_rate(values['recall_at_3'])} | {format_rate(values['precision_at_3'])} | {values['ndcg_at_5']:.3f} | {values['mrr_at_10']:.3f} |"
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
                f"- Frozen relevant chunks: `{', '.join(sorted(case['qrelGrades']))}`",
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
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS, help="Frozen chunk-level qrels JSONL path.")
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLIT_MANIFEST, help="Fixed dev/test split manifest path.")
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST, help="Frozen corpus manifest path.")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="test", help="Evaluation split; test is the default release gate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT, help="Markdown report output path.")
    parser.add_argument("--metrics-output", type=Path, help="Machine-readable JSON metrics output path (defaults beside --output).")
    parser.add_argument("--top-k", type=int, default=10, choices=range(1, 51), metavar="1..50", help="Search candidate depth.")
    parser.add_argument("--mode", choices=["TEXT", "VECTOR", "HYBRID"], default="TEXT", help="Retrieval path to evaluate.")
    parser.add_argument("--endpoint", choices=["search", "ask"], default="search", help="API endpoint to evaluate.")
    parser.add_argument("--graph", choices=["enabled", "disabled"], default="enabled", help="Enable graph expansion for HYBRID evaluation.")
    parser.add_argument("--revision", default=os.getenv("EVAL_REVISION", "unknown"), help="Source commit or revision recorded in the metric payload.")
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
        all_items = load_dataset(args.dataset)
        splits = load_split_manifest(args.split_manifest, args.dataset, {item["id"] for item in all_items})
        corpus = load_corpus_manifest(args.corpus_manifest, args.fixture_dir)
        qrels = load_qrels(args.qrels, all_items, corpus)
        items = select_split(all_items, splits, args.split)
        if args.validate_only:
            print(f"evaluation assets are valid: {len(items)} {args.split} cases, {len(qrels)} frozen qrels")
            return 0

        api_url = args.api_url.rstrip("/")
        graph_enabled = args.graph == "enabled"
        if args.bootstrap:
            uploaded = bootstrap_fixtures(api_url, args.fixture_dir, corpus, args.mode)
            print(f"fixture bootstrap complete; uploaded {len(uploaded)} file(s)")
        runtime_config = request_json(f"{api_url}/runtime/config")
        expected_chunking = load_json_object(args.corpus_manifest, "corpus manifest")["chunking"]
        if runtime_config.get("chunkSize") != expected_chunking["chunkSize"] or runtime_config.get("chunkOverlap") != expected_chunking["chunkOverlap"]:
            raise RuntimeError("API chunk configuration does not match the frozen corpus manifest")

        cases = []
        for item in items:
            if args.endpoint == "search":
                query = urlencode({
                    "q": item["query"], "topK": args.top_k, "mode": args.mode, "graphEnabled": str(graph_enabled).lower(),
                })
                response = request_json(f"{api_url}/search?{query}")
            else:
                response = request_json(
                    f"{api_url}/ask",
                    method="POST",
                    body=json.dumps({"q": item["query"], "topK": args.top_k, "graphEnabled": graph_enabled}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
            cases.append(evaluate_item(item, response, args.top_k, qrels))

        metrics = calculate_metrics(cases)
        report = render_report(cases, metrics, api_url, args.top_k, args.mode, args.endpoint, graph_enabled, args.split)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        metrics_output = args.metrics_output or args.output.with_suffix(".json")
        metrics_output.write_text(
            json.dumps(
                build_metrics_payload(
                    metrics,
                    cases,
                    args.dataset,
                    args.qrels,
                    args.split_manifest,
                    args.corpus_manifest,
                    args.split,
                    api_url,
                    args.top_k,
                    args.mode,
                    args.endpoint,
                    graph_enabled,
                    runtime_config,
                    args.revision,
                ),
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(report)
        print(f"report written to {args.output}")
        print(f"metrics written to {metrics_output}")
        return 0
    except (OSError, RuntimeError, ValueError) as e:
        print(f"retrieval evaluation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
