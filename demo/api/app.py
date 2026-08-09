import os
import re
import uuid
import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Protocol, Set
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from opensearchpy import OpenSearch
from pypdf import PdfReader
from docx import Document

from embedding import EmbeddingProvider, SentenceTransformerEmbeddingProvider


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
META_PATH = DATA_DIR / "meta.json"
CONFIG_PATH = DATA_DIR / "config.json"
ASK_EVENT_LOG_PATH = DATA_DIR / "ask_events.jsonl"

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "kb_demo_chunks")
VECTOR_INDEX_NAME = os.getenv("OPENSEARCH_VECTOR_INDEX", "kb_demo_chunks_vector_v1")
GRAPH_INDEX_NAME = os.getenv("OPENSEARCH_GRAPH_INDEX", "kb_demo_evidence_graph_v1")

SUPPORTED_SUFFIXES = {".txt", ".md", ".log", ".pdf", ".docx"}


def read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer") from e
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than 0")
    return value


def read_non_negative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer") from e
    if value < 0:
        raise RuntimeError(f"{name} must be greater than or equal to 0")
    return value


def read_non_negative_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be a number") from e
    if value < 0:
        raise RuntimeError(f"{name} must be greater than or equal to 0")
    return value


CHUNK_SIZE = read_positive_int_env("CHUNK_SIZE", 800)
CHUNK_OVERLAP = read_non_negative_int_env("CHUNK_OVERLAP", 120)
MAX_UPLOAD_BYTES = read_positive_int_env("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)

if CHUNK_OVERLAP >= CHUNK_SIZE:
    raise RuntimeError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
EMBEDDING_DIMENSION = read_positive_int_env("EMBEDDING_DIMENSION", 384)
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
HYBRID_CANDIDATE_K = read_positive_int_env("HYBRID_CANDIDATE_K", 20)
HYBRID_RRF_K = read_non_negative_int_env("HYBRID_RRF_K", 60)
GRAPH_RRF_WEIGHT = read_non_negative_float_env("GRAPH_RRF_WEIGHT", 0.1)
NO_ANSWER_MIN_TEXT_SCORE = read_non_negative_float_env("NO_ANSWER_MIN_TEXT_SCORE", 4.0)
GRAPH_SEED_LIMIT = read_positive_int_env("GRAPH_SEED_LIMIT", 3)
GRAPH_MAX_PATHS = read_positive_int_env("GRAPH_MAX_PATHS", 8)
ASK_MAX_CITATIONS = read_positive_int_env("ASK_MAX_CITATIONS", 3)
ASK_CONTEXT_CHAR_LIMIT = read_positive_int_env("ASK_CONTEXT_CHAR_LIMIT", 2400)
LLM_API_URL = os.getenv("LLM_API_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT_SECONDS = read_positive_int_env("LLM_TIMEOUT_SECONDS", 30)

GRAPH_ENTITY_MIN_CHARS = 3
GRAPH_ENTITY_MAX_CHARS = 6
GRAPH_ENTITY_STOP_TERMS = {"公司", "员工", "部门", "负责", "需要", "可以", "应当", "必须"}
GRAPH_ENTITY_PREFERRED_SUFFIXES = ("申请", "审批", "报告", "负责人", "指挥官", "认证", "数据", "设备", "合同", "发票", "预算", "费用", "票据", "行程单")
RELATION_QUERY_CUES = ("关联", "关系", "流程", "负责", "谁", "审批", "原因", "为什么")

app = FastAPI(title="KB Demo API (Sanitized)", version="0.1.0")
embedding_provider: Optional[EmbeddingProvider] = None


class AnswerGenerator(Protocol):
    def generate(self, question: str, context: str) -> str:
        """Generate a grounded answer from the supplied evidence context."""


class OpenAICompatibleAnswerGenerator:
    def generate(self, question: str, context: str) -> str:
        if not (LLM_API_URL and LLM_API_KEY and LLM_MODEL):
            raise RuntimeError("LLM_API_URL, LLM_API_KEY, and LLM_MODEL must all be configured")
        prompt = (
            "Answer the question using only the evidence below. Do not add facts not present in the evidence. "
            "Write in the language of the question and cite each factual statement with the provided source label.\n\n"
            f"Question: {question}\n\nEvidence:\n{context}"
        )
        payload = json.dumps({
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode("utf-8")
        request = Request(
            LLM_API_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError) as error:
            raise RuntimeError("grounded LLM request failed") from error
        try:
            answer = body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError, TypeError) as error:
            raise RuntimeError("LLM response did not contain a chat completion") from error
        if not answer:
            raise RuntimeError("LLM returned an empty answer")
        return answer


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not META_PATH.exists():
        META_PATH.write_text(json.dumps({"files": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(
                {"indexMode": "TEXT", "configText": "{}", "vectorIndexConfig": "{}"},
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

def load_meta() -> Dict[str, Any]:
    ensure_dirs()
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def save_meta(meta: Dict[str, Any]) -> None:
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def load_config() -> Dict[str, Any]:
    ensure_dirs()
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def append_ask_event(event: Dict[str, Any]) -> None:
    ensure_dirs()
    with ASK_EVENT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_ask_events() -> List[Dict[str, Any]]:
    if not ASK_EVENT_LOG_PATH.exists():
        return []
    events = []
    for line in ASK_EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def query_fingerprint(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_ask_event(request_id: str, question: str, response: Dict[str, Any]) -> None:
    candidate_ranks = []
    for result in response.get("results", [])[:5]:
        chunk_id = result.get("chunkId")
        if not chunk_id:
            continue
        candidate_ranks.append({
            "chunkId": chunk_id,
            "rank": result.get("rank"),
            "textRank": result.get("textRank"),
            "vectorRank": result.get("vectorRank"),
            "graphRank": result.get("graphRank"),
        })
    append_ask_event({
        "eventType": "ask",
        "timestamp": utc_timestamp(),
        "requestId": request_id,
        "queryFingerprint": query_fingerprint(question),
        "queryLength": len(question),
        "decision": response.get("decision"),
        "answerMode": response.get("answerMode"),
        "retrievedCount": response.get("retrievedCount", 0),
        "citationCount": len(response.get("citations", [])),
        "graphRouted": bool(response.get("graphRouted")),
        "graphRouteReason": response.get("graphRouteReason"),
        "graphCandidateOverlap": response.get("graphCandidateOverlap"),
        "retrievalLatencyMs": response.get("retrievalLatencyMs"),
        "candidateRanks": candidate_ranks,
        "citationChunkIds": [citation.get("chunkId") for citation in response.get("citations", []) if citation.get("chunkId")],
    })


def request_id_exists(request_id: str) -> bool:
    return any(
        event.get("eventType") == "ask" and event.get("requestId") == request_id
        for event in load_ask_events()
    )


def feedback_summary() -> Dict[str, Any]:
    events = load_ask_events()
    ask_events = [event for event in events if event.get("eventType") == "ask"]
    feedback_events = [event for event in events if event.get("eventType") == "feedback"]
    positive_feedback = sum(event.get("rating") == "UP" for event in feedback_events)
    negative_feedback = sum(event.get("rating") == "DOWN" for event in feedback_events)
    answered = sum(event.get("decision") == "ANSWER" for event in ask_events)
    return {
        "askCount": len(ask_events),
        "answerCount": answered,
        "noAnswerCount": len(ask_events) - answered,
        "feedbackCount": len(feedback_events),
        "positiveFeedbackCount": positive_feedback,
        "negativeFeedbackCount": negative_feedback,
        "positiveFeedbackRate": positive_feedback / len(feedback_events) if feedback_events else None,
    }


def feedback_review_queue(limit: int = 20) -> Dict[str, Any]:
    """Return privacy-minimized cases that need a human evaluation-set review."""
    events = load_ask_events()
    feedback_by_request: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        if event.get("eventType") == "feedback":
            feedback_by_request.setdefault(str(event.get("requestId", "")), []).append(event)

    items = []
    for event in events:
        if event.get("eventType") != "ask":
            continue
        feedback = feedback_by_request.get(str(event.get("requestId", "")), [])
        reasons = []
        if event.get("decision") == "NO_ANSWER":
            reasons.append("no_answer")
        if any(item.get("rating") == "DOWN" for item in feedback):
            reasons.append("negative_feedback")
        if not reasons:
            continue
        items.append({
            "requestId": event.get("requestId"),
            "timestamp": event.get("timestamp"),
            "queryFingerprint": event.get("queryFingerprint"),
            "queryLength": event.get("queryLength"),
            "reasons": reasons,
            "decision": event.get("decision"),
            "graphRouted": event.get("graphRouted"),
            "graphRouteReason": event.get("graphRouteReason"),
            "retrievalLatencyMs": event.get("retrievalLatencyMs"),
            "candidateRanks": event.get("candidateRanks", []),
            "ratings": [item.get("rating") for item in feedback],
        })
    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return {"reviewCount": len(items), "items": items[:limit]}

def connect_os() -> OpenSearch:
    # OpenSearch security plugin disabled in compose, so no auth.
    return OpenSearch(OPENSEARCH_URL)


def create_index_if_needed(client: OpenSearch) -> None:
    if client.indices.exists(INDEX_NAME):
        return

    body = {
        "mappings": {
            "properties": {
                "fileId": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "chunkId": {"type": "keyword"},
                "chunkIndex": {"type": "integer"},
                "content": {"type": "text"},
            }
        }
    }
    client.indices.create(index=INDEX_NAME, body=body)


def create_vector_index_if_needed(client: OpenSearch) -> None:
    if client.indices.exists(VECTOR_INDEX_NAME):
        return

    body = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "fileId": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "chunkId": {"type": "keyword"},
                "chunkIndex": {"type": "integer"},
                "content": {"type": "text"},
                "embeddingModel": {"type": "keyword"},
                "contentVector": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIMENSION,
                    "space_type": "l2",
                },
            }
        },
    }
    client.indices.create(index=VECTOR_INDEX_NAME, body=body)


def create_graph_index_if_needed(client: OpenSearch) -> None:
    if client.indices.exists(GRAPH_INDEX_NAME):
        return

    body = {
        "mappings": {
            "properties": {
                "edgeId": {"type": "keyword"},
                "relation": {"type": "keyword"},
                "fromId": {"type": "keyword"},
                "toId": {"type": "keyword"},
                "fromType": {"type": "keyword"},
                "toType": {"type": "keyword"},
                "fileId": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "chunkId": {"type": "keyword"},
                "chunkIndex": {"type": "integer"},
                "entity": {"type": "keyword"},
                "contentPreview": {"type": "text"},
            }
        }
    }
    client.indices.create(index=GRAPH_INDEX_NAME, body=body)


def delete_chunks_for_file_ids(client: OpenSearch, index_name: str, file_ids: List[str]) -> int:
    if not file_ids:
        return 0

    body = {
        "query": {
            "terms": {
                "fileId": file_ids
            }
        }
    }
    resp = client.delete_by_query(
        index=index_name,
        body=body,
        conflicts="proceed",
        refresh=True,
    )
    return int(resp.get("deleted", 0))


def get_embedding_provider() -> EmbeddingProvider:
    global embedding_provider
    if embedding_provider is None:
        embedding_provider = SentenceTransformerEmbeddingProvider(
            model_name=EMBEDDING_MODEL,
            device=EMBEDDING_DEVICE,
        )
    return embedding_provider


def embed_texts(texts: List[str]) -> List[List[float]]:
    try:
        vectors = get_embedding_provider().embed(texts)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if len(vectors) != len(texts):
        raise HTTPException(status_code=500, detail="embedding provider returned an unexpected vector count")
    for vector in vectors:
        if len(vector) != EMBEDDING_DIMENSION:
            raise HTTPException(
                status_code=500,
                detail=(
                    "embedding dimension mismatch; "
                    f"expected {EMBEDDING_DIMENSION}, got {len(vector)}"
                ),
            )
    return vectors


def clean_text(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be greater than or equal to 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in [".txt", ".md", ".log"]:
        return file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        pages = []
        for p in reader.pages:
            pages.append(p.extract_text() or "")
        return "\n".join(pages)

    if suffix in [".docx"]:
        doc = Document(str(file_path))
        return "\n".join([p.text for p in doc.paragraphs])

    raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}")


def content_preview(content: str, limit: int = 160) -> str:
    if len(content) <= limit:
        return content
    return content[:limit] + "..."


def extract_graph_entity_candidates(content: str) -> Set[str]:
    """Extract source-text spans that may form high-confidence shared entities."""
    entities: Set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{%d,}" % GRAPH_ENTITY_MIN_CHARS, content):
        for size in range(GRAPH_ENTITY_MIN_CHARS, min(GRAPH_ENTITY_MAX_CHARS, len(run)) + 1):
            for start in range(0, len(run) - size + 1):
                entity = run[start:start + size]
                if entity not in GRAPH_ENTITY_STOP_TERMS:
                    entities.add(entity)
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{1,}\b|\bP\d+\b", content):
        entities.add(token.lower())
    return entities


def graph_entity_sort_key(entity: str):
    return (0 if entity.endswith(GRAPH_ENTITY_PREFERRED_SUFFIXES) else 1, -len(entity), entity)


def shared_entities_by_chunk(chunk_records: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    entity_chunks: Dict[str, Set[str]] = {}
    for record in chunk_records:
        chunk_id = str(record["chunkId"])
        for entity in extract_graph_entity_candidates(record["content"]):
            entity_chunks.setdefault(entity, set()).add(chunk_id)

    shared_entities = {
        entity for entity, chunk_ids in entity_chunks.items()
        if len(chunk_ids) >= 2
    }
    by_chunk: Dict[str, List[str]] = {}
    for record in chunk_records:
        chunk_id = str(record["chunkId"])
        entities = sorted(
            (entity for entity in extract_graph_entity_candidates(record["content"]) if entity in shared_entities),
            key=graph_entity_sort_key,
        )
        by_chunk[chunk_id] = entities[:12]
    return by_chunk


def build_graph_records(chunk_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create source-grounded document/chunk/entity edges for OpenSearch."""
    entity_map = shared_entities_by_chunk(chunk_records)
    edges: List[Dict[str, Any]] = []
    records_by_file: Dict[str, List[Dict[str, Any]]] = {}
    for record in chunk_records:
        records_by_file.setdefault(str(record["fileId"]), []).append(record)

    for file_id, records in records_by_file.items():
        records.sort(key=lambda record: int(record["chunkIndex"]))
        document_id = f"document:{file_id}"
        for record in records:
            chunk_id = str(record["chunkId"])
            common = {
                "fileId": file_id,
                "filename": record["filename"],
                "chunkId": chunk_id,
                "chunkIndex": record["chunkIndex"],
                "contentPreview": content_preview(record["content"]),
            }
            edges.append({
                **common,
                "edgeId": f"{document_id}:contains:{chunk_id}",
                "relation": "CONTAINS",
                "fromId": document_id,
                "toId": chunk_id,
                "fromType": "DOCUMENT",
                "toType": "CHUNK",
            })
            for entity in entity_map.get(chunk_id, []):
                edges.append({
                    **common,
                    "edgeId": f"{chunk_id}:mentions:{entity}",
                    "relation": "MENTIONS",
                    "fromId": chunk_id,
                    "toId": f"entity:{entity}",
                    "fromType": "CHUNK",
                    "toType": "ENTITY",
                    "entity": entity,
                })
        for current, following in zip(records, records[1:]):
            edges.append({
                "edgeId": f"{current['chunkId']}:next:{following['chunkId']}",
                "relation": "NEXT_CHUNK",
                "fromId": current["chunkId"],
                "toId": following["chunkId"],
                "fromType": "CHUNK",
                "toType": "CHUNK",
                "fileId": file_id,
                "filename": current["filename"],
                "chunkId": current["chunkId"],
                "chunkIndex": current["chunkIndex"],
                "contentPreview": content_preview(following["content"]),
            })
    return edges


def is_relationship_query(query: str) -> bool:
    return any(cue in query for cue in RELATION_QUERY_CUES)


def candidate_overlap_count(text_hits: List[Dict[str, Any]], vector_hits: List[Dict[str, Any]]) -> int:
    text_ids = {hit_chunk_id(hit) for hit in text_hits[:GRAPH_SEED_LIMIT] if hit_chunk_id(hit)}
    vector_ids = {hit_chunk_id(hit) for hit in vector_hits[:GRAPH_SEED_LIMIT] if hit_chunk_id(hit)}
    return len(text_ids & vector_ids)


def graph_route_decision(
    query: str,
    text_hits: List[Dict[str, Any]],
    vector_hits: List[Dict[str, Any]],
    answer_decision: Dict[str, Any],
) -> Dict[str, Any]:
    """Route only when a relation cue or independent candidates justify graph cost."""
    overlap = candidate_overlap_count(text_hits, vector_hits)
    if answer_decision.get("status") != "ANSWER":
        return {"routed": False, "reason": "no_answer", "candidateOverlap": overlap}
    if is_relationship_query(query):
        return {"routed": True, "reason": "relationship_query_cue", "candidateOverlap": overlap}
    if not overlap:
        return {"routed": True, "reason": "candidate_disagreement", "candidateOverlap": overlap}
    return {"routed": False, "reason": "candidate_agreement", "candidateOverlap": overlap}


def filter_graph_seed_edges_by_query(query: str, edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    query_entities = extract_graph_entity_candidates(query)
    matching_edges = [
        edge for edge in edges
        if edge.get("_source", {}).get("entity") in query_entities
    ]
    if not matching_edges:
        return edges
    best_key = min(graph_entity_sort_key(str(edge.get("_source", {}).get("entity", ""))) for edge in matching_edges)
    return [
        edge for edge in matching_edges
        if graph_entity_sort_key(str(edge.get("_source", {}).get("entity", ""))) == best_key
    ]


def text_search_body(query: str, size: int) -> Dict[str, Any]:
    return {
        "size": size,
        "query": {"match": {"content": query}},
        "highlight": {
            "fields": {"content": {}},
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }


def vector_search_body(query_vector: List[float], size: int) -> Dict[str, Any]:
    return {
        "size": size,
        "query": {
            "knn": {
                "contentVector": {
                    "vector": query_vector,
                    "k": size,
                }
            }
        },
    }


def hit_chunk_id(hit: Dict[str, Any]) -> str:
    source = hit.get("_source", {})
    return str(source.get("chunkId") or hit.get("_id") or "")


def fuse_ranked_hits(
    text_hits: List[Dict[str, Any]],
    vector_hits: List[Dict[str, Any]],
    top_k: int,
    graph_hits: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Fuse text and vector candidates with reciprocal rank fusion (RRF)."""
    candidates: Dict[str, Dict[str, Any]] = {}

    def add_hits(hits: List[Dict[str, Any]], rank_key: str, score_key: str, weight: float = 1.0) -> None:
        for rank, hit in enumerate(hits, start=1):
            chunk_id = hit_chunk_id(hit)
            if not chunk_id:
                continue
            candidate = candidates.setdefault(
                chunk_id,
                {
                    "hit": hit,
                    "textRank": None,
                    "vectorRank": None,
                    "graphRank": None,
                    "textScore": None,
                    "vectorScore": None,
                    "graphScore": None,
                    "fusionScore": 0.0,
                },
            )
            candidate[rank_key] = rank
            candidate[score_key] = hit.get("_score")
            # Graph evidence may fill a retrieval gap, but must not reorder a chunk
            # that already has direct BM25 or vector evidence.
            if rank_key == "graphRank" and (candidate["textRank"] is not None or candidate["vectorRank"] is not None):
                continue
            candidate["fusionScore"] += weight / (HYBRID_RRF_K + rank)

    add_hits(text_hits, "textRank", "textScore")
    add_hits(vector_hits, "vectorRank", "vectorScore")
    add_hits(graph_hits or [], "graphRank", "graphScore", GRAPH_RRF_WEIGHT)
    return sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate["fusionScore"],
            min(
                rank
                for rank in [candidate["textRank"], candidate["vectorRank"], candidate["graphRank"]]
                if rank is not None
            ),
            hit_chunk_id(candidate["hit"]),
        ),
    )[:top_k]


def format_search_result(
    hit: Dict[str, Any],
    rank: int,
    text_rank: Optional[int] = None,
    vector_rank: Optional[int] = None,
    graph_rank: Optional[int] = None,
    fusion_score: Optional[float] = None,
    text_score: Optional[float] = None,
    vector_score: Optional[float] = None,
    graph_score: Optional[float] = None,
) -> Dict[str, Any]:
    source = hit.get("_source", {})
    highlight = hit.get("highlight", {}).get("content", [])
    content = source.get("content", "") or ""
    return {
        "rank": rank,
        "fileId": source.get("fileId"),
        "filename": source.get("filename"),
        "chunkId": source.get("chunkId"),
        "chunkIndex": source.get("chunkIndex"),
        "score": fusion_score if fusion_score is not None else hit.get("_score"),
        "textRank": text_rank,
        "vectorRank": vector_rank,
        "graphRank": graph_rank,
        "fusionScore": fusion_score,
        "textScore": text_score,
        "vectorScore": vector_score,
        "graphScore": graph_score,
        "highlight": highlight[0] if highlight else None,
        "content": content,
        "contentPreview": content_preview(content),
    }


def decide_answer(mode: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a small, inspectable answer decision without generating text."""
    if not results:
        return {
            "status": "NO_ANSWER",
            "reason": "no_retrieval_candidates",
            "evidence": {"retrievedCount": 0},
        }

    if mode != "HYBRID":
        return {
            "status": "ANSWER",
            "reason": "single_path_retrieval_not_gated",
            "evidence": {"retrievedCount": len(results)},
        }

    text_scores = [
        float(result["textScore"])
        for result in results
        if result.get("textScore") is not None
    ]
    max_text_score = max(text_scores, default=0.0)
    supporting_chunks = sum(score >= NO_ANSWER_MIN_TEXT_SCORE for score in text_scores)
    evidence = {
        "retrievedCount": len(results),
        "maxTextScore": max_text_score,
        "minTextScore": NO_ANSWER_MIN_TEXT_SCORE,
        "supportingChunkCount": supporting_chunks,
    }
    if supporting_chunks == 0:
        return {
            "status": "NO_ANSWER",
            "reason": "insufficient_lexical_evidence",
            "evidence": evidence,
        }
    return {
        "status": "ANSWER",
        "reason": "hybrid_lexical_evidence_above_threshold",
        "evidence": evidence,
    }


def build_citations(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations = []
    seen_chunk_ids = set()
    for result in results:
        chunk_id = result.get("chunkId")
        if not chunk_id or chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        citations.append({
            "citationId": len(citations) + 1,
            "fileId": result.get("fileId"),
            "filename": result.get("filename"),
            "chunkId": chunk_id,
            "chunkIndex": result.get("chunkIndex"),
            "contentPreview": result.get("contentPreview"),
        })
        if len(citations) >= ASK_MAX_CITATIONS:
            break
    return citations


def build_answer_context(citations: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> str:
    content_by_chunk_id = {result.get("chunkId"): result.get("content", "") for result in results}
    sections = []
    remaining = ASK_CONTEXT_CHAR_LIMIT
    for citation in citations:
        content = str(content_by_chunk_id.get(citation["chunkId"], ""))
        if not content or remaining <= 0:
            continue
        excerpt = content[:remaining]
        sections.append(f"[{citation['filename']}#{citation['chunkId']}]\n{excerpt}")
        remaining -= len(excerpt)
    return "\n\n".join(sections)


def compose_grounded_answer(
    question: str,
    retrieval: Dict[str, Any],
    generator: Optional[AnswerGenerator] = None,
) -> Dict[str, Any]:
    if retrieval.get("decision") != "ANSWER":
        return {
            "answer": "No grounded answer is available in the knowledge base.",
            "answerMode": "NO_ANSWER",
            "answerReason": retrieval.get("decisionReason"),
            "citations": [],
        }

    results = retrieval.get("results", [])
    citations = build_citations(results)
    if not citations:
        return {
            "answer": "No grounded answer is available in the knowledge base.",
            "answerMode": "NO_ANSWER",
            "answerReason": "no_citable_evidence",
            "citations": [],
        }

    context = build_answer_context(citations, results)
    if generator is not None:
        try:
            return {
                "answer": generator.generate(question, context),
                "answerMode": "LLM",
                "answerReason": "grounded_llm_completion",
                "citations": citations,
            }
        except RuntimeError:
            pass

    first_citation = citations[0]
    return {
        "answer": f"Evidence from {first_citation['filename']}: {first_citation['contentPreview']}",
        "answerMode": "EXTRACTIVE",
        "answerReason": "llm_not_configured_or_unavailable",
        "citations": citations,
    }


def get_answer_generator() -> Optional[AnswerGenerator]:
    if not (LLM_API_URL and LLM_API_KEY and LLM_MODEL):
        return None
    return OpenAICompatibleAnswerGenerator()


@app.get("/health")
def health():
    ensure_dirs()
    try:
        client = connect_os()
        info = client.info()
        return {"ok": True, "opensearch": info.get("version", {}).get("number", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ensure_dirs()

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    file_id = str(uuid.uuid4())
    safe_name = Path(file.filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}; allowed: {allowed}")

    dst = UPLOAD_DIR / f"{file_id}__{safe_name}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"file too large; max bytes: {MAX_UPLOAD_BYTES}")

    dst.write_bytes(content)

    meta = load_meta()
    meta["files"].append({"fileId": file_id, "filename": safe_name, "path": str(dst)})
    save_meta(meta)

    return {"fileId": file_id, "filename": safe_name}


@app.get("/files")
def list_files():
    files = load_meta().get("files", [])
    return {
        "count": len(files),
        "files": [
            {"fileId": f.get("fileId"), "filename": f.get("filename")}
            for f in files
        ],
    }


@app.get("/index/config")
def get_index_config():
    return load_config()

@app.post("/index/config")
def set_index_config(body: Dict[str, Any]):
    """
    body example:
    {
      "indexMode": "TEXT" | "VECTOR" | "HYBRID",
      "configText": "{}",
      "vectorIndexConfig": "{}"
    }
    """
    cfg = load_config()
    mode = (body.get("indexMode") or cfg.get("indexMode") or "TEXT").upper()

    if mode not in ["TEXT", "VECTOR", "HYBRID"]:
        raise HTTPException(status_code=400, detail="indexMode must be TEXT | VECTOR | HYBRID")

    cfg["indexMode"] = mode
    if "configText" in body:
        cfg["configText"] = body["configText"]
    if "vectorIndexConfig" in body:
        cfg["vectorIndexConfig"] = body["vectorIndexConfig"]

    save_config(cfg)
    return {"ok": True, "config": cfg}

@app.post("/reindex")
def reindex(fileId: Optional[str] = None):
    """
    Reindex all uploaded files by default.
    Optional: reindex a single file by fileId.
    """
    ensure_dirs()
    client = connect_os()
    create_index_if_needed(client)

    meta = load_meta()
    files = meta.get("files", [])
    if fileId:
        files = [f for f in files if f.get("fileId") == fileId]
        if not files:
            raise HTTPException(status_code=404, detail=f"fileId not found: {fileId}")

    rebuild_file_ids = [str(f.get("fileId")) for f in files if f.get("fileId")]
    deleted_chunks = delete_chunks_for_file_ids(client, INDEX_NAME, rebuild_file_ids)

    # build bulk actions
    bulk_lines: List[str] = []
    total_chunks = 0

    for f in files:
        path = Path(f["path"])
        if not path.exists():
            continue
        raw = extract_text(path)
        text = clean_text(raw)
        chunks = split_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, c in enumerate(chunks):
            chunk_id = f'{f["fileId"]}:{i}'
            bulk_lines.append(json.dumps({"index": {"_index": INDEX_NAME, "_id": chunk_id}}, ensure_ascii=False))
            bulk_lines.append(json.dumps({
                "fileId": f["fileId"],
                "filename": f["filename"],
                "chunkId": chunk_id,
                "chunkIndex": i,
                "content": c,
            }, ensure_ascii=False))
        total_chunks += len(chunks)

    if total_chunks == 0:
        return {"ok": True, "indexedChunks": 0, "deletedChunks": deleted_chunks, "index": INDEX_NAME}

    payload = "\n".join(bulk_lines) + "\n"
    resp = client.bulk(body=payload, headers={"Content-Type": "application/x-ndjson"})
    if resp.get("errors"):
        # return a small hint only (avoid dumping internal response)
        raise HTTPException(status_code=500, detail="bulk index returned errors=true")

    client.indices.refresh(index=INDEX_NAME)
    return {"ok": True, "indexedChunks": total_chunks, "deletedChunks": deleted_chunks, "index": INDEX_NAME}


def vector_reindex(fileId: Optional[str] = None):
    """Build a separate OpenSearch k-NN index from uploaded source files."""
    ensure_dirs()
    client = connect_os()
    create_vector_index_if_needed(client)

    meta = load_meta()
    files = meta.get("files", [])
    if fileId:
        files = [f for f in files if f.get("fileId") == fileId]
        if not files:
            raise HTTPException(status_code=404, detail=f"fileId not found: {fileId}")

    rebuild_file_ids = [str(f.get("fileId")) for f in files if f.get("fileId")]
    deleted_chunks = delete_chunks_for_file_ids(client, VECTOR_INDEX_NAME, rebuild_file_ids)

    chunk_records = []
    for f in files:
        path = Path(f["path"])
        if not path.exists():
            continue
        text = clean_text(extract_text(path))
        for i, content in enumerate(split_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunk_records.append({
                "fileId": f["fileId"],
                "filename": f["filename"],
                "chunkId": f'{f["fileId"]}:{i}',
                "chunkIndex": i,
                "content": content,
            })

    if not chunk_records:
        return {
            "ok": True,
            "indexedChunks": 0,
            "deletedChunks": deleted_chunks,
            "index": VECTOR_INDEX_NAME,
            "embeddingModel": EMBEDDING_MODEL,
            "embeddingDimension": EMBEDDING_DIMENSION,
        }

    vectors = embed_texts([record["content"] for record in chunk_records])
    bulk_lines: List[str] = []
    for record, vector in zip(chunk_records, vectors):
        bulk_lines.append(json.dumps({"index": {"_index": VECTOR_INDEX_NAME, "_id": record["chunkId"]}}, ensure_ascii=False))
        bulk_lines.append(json.dumps({
            **record,
            "embeddingModel": EMBEDDING_MODEL,
            "contentVector": vector,
        }, ensure_ascii=False))

    resp = client.bulk(
        body="\n".join(bulk_lines) + "\n",
        headers={"Content-Type": "application/x-ndjson"},
    )
    if resp.get("errors"):
        raise HTTPException(status_code=500, detail="vector bulk index returned errors=true")

    client.indices.refresh(index=VECTOR_INDEX_NAME)
    return {
        "ok": True,
        "indexedChunks": len(chunk_records),
        "deletedChunks": deleted_chunks,
        "index": VECTOR_INDEX_NAME,
        "embeddingModel": EMBEDDING_MODEL,
        "embeddingDimension": EMBEDDING_DIMENSION,
    }


def graph_reindex(fileId: Optional[str] = None):
    """Build source-grounded document, chunk, and shared-entity graph edges."""
    ensure_dirs()
    client = connect_os()
    create_graph_index_if_needed(client)

    files = load_meta().get("files", [])
    if fileId:
        files = [file for file in files if file.get("fileId") == fileId]
        if not files:
            raise HTTPException(status_code=404, detail=f"fileId not found: {fileId}")

    rebuild_file_ids = [str(file.get("fileId")) for file in files if file.get("fileId")]
    deleted_edges = delete_chunks_for_file_ids(client, GRAPH_INDEX_NAME, rebuild_file_ids)
    chunk_records = []
    for file in files:
        path = Path(file["path"])
        if not path.exists():
            continue
        text = clean_text(extract_text(path))
        for index, content in enumerate(split_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunk_records.append({
                "fileId": file["fileId"],
                "filename": file["filename"],
                "chunkId": f'{file["fileId"]}:{index}',
                "chunkIndex": index,
                "content": content,
            })

    graph_records = build_graph_records(chunk_records)
    if not graph_records:
        return {"ok": True, "indexedEdges": 0, "deletedEdges": deleted_edges, "index": GRAPH_INDEX_NAME}

    bulk_lines: List[str] = []
    for record in graph_records:
        bulk_lines.append(json.dumps({"index": {"_index": GRAPH_INDEX_NAME, "_id": record["edgeId"]}}, ensure_ascii=False))
        bulk_lines.append(json.dumps(record, ensure_ascii=False))
    response = client.bulk(
        body="\n".join(bulk_lines) + "\n",
        headers={"Content-Type": "application/x-ndjson"},
    )
    if response.get("errors"):
        raise HTTPException(status_code=500, detail="graph bulk index returned errors=true")
    client.indices.refresh(index=GRAPH_INDEX_NAME)
    return {"ok": True, "indexedEdges": len(graph_records), "deletedEdges": deleted_edges, "index": GRAPH_INDEX_NAME}


def graph_expand(client: OpenSearch, query: str, seed_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not client.indices.exists(GRAPH_INDEX_NAME):
        return []
    seed_chunk_ids = [
        str(result["chunkId"])
        for result in seed_results[:GRAPH_SEED_LIMIT]
        if result.get("chunkId")
    ]
    if not seed_chunk_ids:
        return []

    seed_edges = client.search(
        index=GRAPH_INDEX_NAME,
        body={
            "size": GRAPH_MAX_PATHS,
            "query": {"bool": {"filter": [
                {"terms": {"fromId": seed_chunk_ids}},
                {"term": {"relation": "MENTIONS"}},
            ]}},
        },
    ).get("hits", {}).get("hits", [])
    seed_edges = filter_graph_seed_edges_by_query(query, seed_edges)
    entity_ids = [edge.get("_source", {}).get("toId") for edge in seed_edges]
    entity_ids = [entity_id for entity_id in entity_ids if entity_id]
    if not entity_ids:
        return []

    target_edges = client.search(
        index=GRAPH_INDEX_NAME,
        body={
            "size": GRAPH_MAX_PATHS * 2,
            "query": {"bool": {"filter": [
                {"terms": {"toId": entity_ids}},
                {"term": {"relation": "MENTIONS"}},
            ]}},
        },
    ).get("hits", {}).get("hits", [])
    paths: List[Dict[str, Any]] = []
    seen = set()
    for seed_edge in seed_edges:
        seed = seed_edge.get("_source", {})
        for target_edge in target_edges:
            target = target_edge.get("_source", {})
            if target.get("toId") != seed.get("toId") or target.get("fromId") == seed.get("fromId"):
                continue
            key = (seed.get("fromId"), target.get("fromId"), seed.get("entity"))
            if key in seen:
                continue
            seen.add(key)
            paths.append({
                "relation": "MENTIONS",
                "entity": seed.get("entity"),
                "fromChunkId": seed.get("fromId"),
                "fromFilename": seed.get("filename"),
                "toChunkId": target.get("fromId"),
                "filename": target.get("filename"),
                "chunkIndex": target.get("chunkIndex"),
                "evidence": target.get("contentPreview"),
            })
            if len(paths) >= GRAPH_MAX_PATHS:
                return paths
    return paths


def graph_candidate_hits(client: OpenSearch, paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve graph path targets back to canonical text chunks before fusion."""
    target_ids = []
    for path in paths:
        chunk_id = path.get("toChunkId")
        if chunk_id and chunk_id not in target_ids:
            target_ids.append(chunk_id)
    if not target_ids:
        return []
    response = client.mget(index=INDEX_NAME, body={"ids": target_ids})
    by_id = {
        str(document.get("_id")): document
        for document in response.get("docs", [])
        if document.get("found")
    }
    return [
        {"_id": chunk_id, "_source": by_id[chunk_id].get("_source", {}), "_score": 1.0}
        for chunk_id in target_ids
        if chunk_id in by_id
    ]


@app.post("/index/rebuild")
def index_rebuild(fileId: Optional[str] = None):
    """
    Rebuild/reconstruct index by indexMode:
    - TEXT   -> OpenSearch full-text reindex (existing /reindex)
    - VECTOR -> vector rebuild (embedding + k-NN index)
    - HYBRID -> text, vector, and source-grounded graph rebuild
    """
    cfg = load_config()
    mode = (cfg.get("indexMode") or "TEXT").upper()

    out = {"ok": True, "indexMode": mode, "steps": {}}

    if mode in ["TEXT", "HYBRID"]:
        out["steps"]["text"] = reindex(fileId=fileId)

    if mode in ["VECTOR", "HYBRID"]:
        out["steps"]["vector"] = vector_reindex(fileId=fileId)

    if mode == "HYBRID":
        out["steps"]["graph"] = graph_reindex(fileId=fileId)

    return out

@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    topK: int = Query(10, ge=1, le=50),
    mode: str = Query("TEXT"),
):
    started_at = time.perf_counter()
    client = connect_os()
    mode = mode.upper()
    if mode not in ["TEXT", "VECTOR", "HYBRID"]:
        raise HTTPException(status_code=400, detail="mode must be TEXT | VECTOR | HYBRID")

    required_indexes = [INDEX_NAME] if mode == "TEXT" else [VECTOR_INDEX_NAME]
    if mode == "HYBRID":
        required_indexes = [INDEX_NAME, VECTOR_INDEX_NAME]
    missing_indexes = [index_name for index_name in required_indexes if not client.indices.exists(index_name)]
    if missing_indexes:
        raise HTTPException(status_code=404, detail=f"index not found: {', '.join(missing_indexes)}")

    response: Dict[str, Any] = {
        "q": q,
        "mode": mode,
        "topK": topK,
        "embeddingModel": EMBEDDING_MODEL if mode in ["VECTOR", "HYBRID"] else None,
    }
    if mode == "TEXT":
        hits = client.search(index=INDEX_NAME, body=text_search_body(q, topK)).get("hits", {}).get("hits", [])
        results = [format_search_result(hit, rank, text_rank=rank) for rank, hit in enumerate(hits, start=1)]
    elif mode == "VECTOR":
        query_vector = embed_texts([q])[0]
        hits = client.search(
            index=VECTOR_INDEX_NAME,
            body=vector_search_body(query_vector, topK),
        ).get("hits", {}).get("hits", [])
        results = [format_search_result(hit, rank, vector_rank=rank) for rank, hit in enumerate(hits, start=1)]
    else:
        candidate_k = max(topK, HYBRID_CANDIDATE_K)
        query_vector = embed_texts([q])[0]
        text_hits = client.search(
            index=INDEX_NAME,
            body=text_search_body(q, candidate_k),
        ).get("hits", {}).get("hits", [])
        vector_hits = client.search(
            index=VECTOR_INDEX_NAME,
            body=vector_search_body(query_vector, candidate_k),
        ).get("hits", {}).get("hits", [])
        fused_candidates = fuse_ranked_hits(text_hits, vector_hits, topK)
        provisional_results = [
            format_search_result(
                candidate["hit"],
                rank,
                text_rank=candidate["textRank"],
                vector_rank=candidate["vectorRank"],
                graph_rank=candidate["graphRank"],
                fusion_score=candidate["fusionScore"],
                text_score=candidate["textScore"],
                vector_score=candidate["vectorScore"],
                graph_score=candidate["graphScore"],
            )
            for rank, candidate in enumerate(fused_candidates, start=1)
        ]
        response.update({"candidateK": candidate_k, "rrfK": HYBRID_RRF_K, "graphRrfWeight": GRAPH_RRF_WEIGHT})

    if mode == "HYBRID":
        decision = decide_answer(mode, provisional_results)
        graph_route = graph_route_decision(q, text_hits, vector_hits, decision)
        graph_evidence = graph_expand(client, q, provisional_results) if graph_route["routed"] else []
        graph_hits = graph_candidate_hits(client, graph_evidence) if graph_evidence else []
        if graph_hits:
            fused_candidates = fuse_ranked_hits(text_hits, vector_hits, topK, graph_hits=graph_hits)
        results = [
            format_search_result(
                candidate["hit"],
                rank,
                text_rank=candidate["textRank"],
                vector_rank=candidate["vectorRank"],
                graph_rank=candidate["graphRank"],
                fusion_score=candidate["fusionScore"],
                text_score=candidate["textScore"],
                vector_score=candidate["vectorScore"],
                graph_score=candidate["graphScore"],
            )
            for rank, candidate in enumerate(fused_candidates, start=1)
        ]
        decision = decide_answer(mode, results)
    else:
        decision = decide_answer(mode, results)
        graph_route = {"routed": False, "reason": "not_hybrid_mode", "candidateOverlap": None}
        graph_evidence = []
    response.update({
        "decision": decision["status"],
        "decisionReason": decision["reason"],
        "decisionEvidence": decision["evidence"],
        "retrievedCount": len(results),
        "count": len(results) if decision["status"] == "ANSWER" else 0,
        "results": results if decision["status"] == "ANSWER" else [],
        "graphRouted": graph_route["routed"],
        "graphRouteReason": graph_route["reason"],
        "graphCandidateOverlap": graph_route["candidateOverlap"],
        "graphEvidence": graph_evidence,
        "retrievalLatencyMs": round((time.perf_counter() - started_at) * 1000, 2),
    })
    return response


@app.post("/ask")
def ask(body: Dict[str, Any]):
    question = body.get("q")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=400, detail="q must be a non-empty string")
    requested_top_k = body.get("topK", 5)
    if not isinstance(requested_top_k, int) or isinstance(requested_top_k, bool) or not 1 <= requested_top_k <= 50:
        raise HTTPException(status_code=400, detail="topK must be an integer from 1 to 50")

    retrieval = search(q=question.strip(), topK=requested_top_k, mode="HYBRID")
    answer = compose_grounded_answer(question.strip(), retrieval, get_answer_generator())
    response = {**retrieval, **answer, "requestId": str(uuid.uuid4())}
    record_ask_event(response["requestId"], question.strip(), response)
    return response


@app.post("/feedback")
def submit_feedback(body: Dict[str, Any]):
    request_id = body.get("requestId")
    rating = body.get("rating")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise HTTPException(status_code=400, detail="requestId must be a non-empty string up to 128 characters")
    if rating not in {"UP", "DOWN"}:
        raise HTTPException(status_code=400, detail="rating must be UP or DOWN")
    if not request_id_exists(request_id):
        raise HTTPException(status_code=404, detail="requestId not found")
    append_ask_event({
        "eventType": "feedback",
        "timestamp": utc_timestamp(),
        "requestId": request_id,
        "rating": rating,
    })
    return {"ok": True, "requestId": request_id, "rating": rating}


@app.get("/feedback/summary")
def get_feedback_summary():
    return feedback_summary()


@app.get("/feedback/review-queue")
def get_feedback_review_queue(limit: int = Query(20, ge=1, le=100)):
    return feedback_review_queue(limit)
