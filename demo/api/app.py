import os
import re
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from opensearchpy import OpenSearch
from pypdf import PdfReader
from docx import Document

from embedding import EmbeddingProvider, SentenceTransformerEmbeddingProvider


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
META_PATH = DATA_DIR / "meta.json"
CONFIG_PATH = DATA_DIR / "config.json"

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "kb_demo_chunks")
VECTOR_INDEX_NAME = os.getenv("OPENSEARCH_VECTOR_INDEX", "kb_demo_chunks_vector_v1")

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
NO_ANSWER_MIN_TEXT_SCORE = read_non_negative_float_env("NO_ANSWER_MIN_TEXT_SCORE", 4.0)

app = FastAPI(title="KB Demo API (Sanitized)", version="0.1.0")
embedding_provider: Optional[EmbeddingProvider] = None


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
) -> List[Dict[str, Any]]:
    """Fuse text and vector candidates with reciprocal rank fusion (RRF)."""
    candidates: Dict[str, Dict[str, Any]] = {}

    def add_hits(hits: List[Dict[str, Any]], rank_key: str, score_key: str) -> None:
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
                    "textScore": None,
                    "vectorScore": None,
                    "fusionScore": 0.0,
                },
            )
            candidate[rank_key] = rank
            candidate[score_key] = hit.get("_score")
            candidate["fusionScore"] += 1.0 / (HYBRID_RRF_K + rank)

    add_hits(text_hits, "textRank", "textScore")
    add_hits(vector_hits, "vectorRank", "vectorScore")
    return sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate["fusionScore"],
            min(rank for rank in [candidate["textRank"], candidate["vectorRank"]] if rank is not None),
            hit_chunk_id(candidate["hit"]),
        ),
    )[:top_k]


def format_search_result(
    hit: Dict[str, Any],
    rank: int,
    text_rank: Optional[int] = None,
    vector_rank: Optional[int] = None,
    fusion_score: Optional[float] = None,
    text_score: Optional[float] = None,
    vector_score: Optional[float] = None,
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
        "fusionScore": fusion_score,
        "textScore": text_score,
        "vectorScore": vector_score,
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


@app.post("/index/rebuild")
def index_rebuild(fileId: Optional[str] = None):
    """
    Rebuild/reconstruct index by indexMode:
    - TEXT   -> OpenSearch full-text reindex (existing /reindex)
    - VECTOR -> vector rebuild (embedding + k-NN index)
    - HYBRID -> both
    """
    cfg = load_config()
    mode = (cfg.get("indexMode") or "TEXT").upper()

    out = {"ok": True, "indexMode": mode, "steps": {}}

    if mode in ["TEXT", "HYBRID"]:
        out["steps"]["text"] = reindex(fileId=fileId)

    if mode in ["VECTOR", "HYBRID"]:
        out["steps"]["vector"] = vector_reindex(fileId=fileId)

    return out

@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    topK: int = Query(10, ge=1, le=50),
    mode: str = Query("TEXT"),
):
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
        results = [
            format_search_result(
                candidate["hit"],
                rank,
                text_rank=candidate["textRank"],
                vector_rank=candidate["vectorRank"],
                fusion_score=candidate["fusionScore"],
                text_score=candidate["textScore"],
                vector_score=candidate["vectorScore"],
            )
            for rank, candidate in enumerate(fused_candidates, start=1)
        ]
        response.update({"candidateK": candidate_k, "rrfK": HYBRID_RRF_K})

    decision = decide_answer(mode, results)
    response.update({
        "decision": decision["status"],
        "decisionReason": decision["reason"],
        "decisionEvidence": decision["evidence"],
        "retrievedCount": len(results),
        "count": len(results) if decision["status"] == "ANSWER" else 0,
        "results": results if decision["status"] == "ANSWER" else [],
    })
    return response
