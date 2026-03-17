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


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
META_PATH = DATA_DIR / "meta.json"
CONFIG_PATH = DATA_DIR / "config.json"

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "kb_demo_chunks")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

app = FastAPI(title="KB Demo API (Sanitized)", version="0.1.0")


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


def clean_text(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
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

    # fallback: try read as text
    return file_path.read_text(encoding="utf-8", errors="ignore")


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
    dst = UPLOAD_DIR / f"{file_id}__{safe_name}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    dst.write_bytes(content)

    meta = load_meta()
    meta["files"].append({"fileId": file_id, "filename": safe_name, "path": str(dst)})
    save_meta(meta)

    return {"fileId": file_id, "filename": safe_name}

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
        return {"ok": True, "indexedChunks": 0}

    payload = "\n".join(bulk_lines) + "\n"
    resp = client.bulk(body=payload, headers={"Content-Type": "application/x-ndjson"})
    if resp.get("errors"):
        # return a small hint only (avoid dumping internal response)
        raise HTTPException(status_code=500, detail="bulk index returned errors=true")

    client.indices.refresh(index=INDEX_NAME)
    return {"ok": True, "indexedChunks": total_chunks, "index": INDEX_NAME}

def vector_rebuild_stub(fileId: Optional[str] = None) -> Dict[str, Any]:
    """
    Demo placeholder:
    - In full system, this would call a vector service (embedding + upsert).
    - Here we just return a stub response so the mode switch is demonstrable.
    """
    return {"ok": True, "mode": "VECTOR", "message": "vector rebuild is stubbed in demo", "fileId": fileId}


@app.post("/index/rebuild")
def index_rebuild(fileId: Optional[str] = None):
    """
    Rebuild/reconstruct index by indexMode:
    - TEXT   -> OpenSearch full-text reindex (existing /reindex)
    - VECTOR -> vector rebuild (stub in demo)
    - HYBRID -> both
    """
    cfg = load_config()
    mode = (cfg.get("indexMode") or "TEXT").upper()

    out = {"ok": True, "indexMode": mode, "steps": {}}

    if mode in ["TEXT", "HYBRID"]:
        out["steps"]["text"] = reindex(fileId=fileId)

    if mode in ["VECTOR", "HYBRID"]:
        out["steps"]["vector"] = vector_rebuild_stub(fileId=fileId)

    return out

@app.get("/search")
def search(q: str = Query(..., min_length=1), topK: int = Query(10, ge=1, le=50)):
    client = connect_os()
    if not client.indices.exists(INDEX_NAME):
        raise HTTPException(status_code=404, detail=f"index not found: {INDEX_NAME}")

    body = {
        "size": topK,
        "query": {"match": {"content": q}},
        "highlight": {
            "fields": {"content": {}},
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }

    resp = client.search(index=INDEX_NAME, body=body)
    hits = resp.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        src = h.get("_source", {})
        hl = h.get("highlight", {}).get("content", [])
        results.append({
            "fileId": src.get("fileId"),
            "filename": src.get("filename"),
            "chunkIndex": src.get("chunkIndex"),
            "score": h.get("_score"),
            "highlight": hl[0] if hl else None,
            "contentPreview": (src.get("content", "")[:160] + "...") if src.get("content") else "",
        })

    return {"q": q, "count": len(results), "results": results}