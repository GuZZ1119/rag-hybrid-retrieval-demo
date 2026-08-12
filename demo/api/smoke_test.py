import asyncio
import importlib
import json
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException


class FakeUploadFile:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


class FakeEmbeddingProvider:
    def __init__(self, dimension):
        self.dimension = dimension
        self.requests = []

    def embed(self, texts):
        self.requests.append(texts)
        return [[0.0] * self.dimension for _ in texts]


class FakeAnswerGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, question, context):
        self.calls.append((question, context))
        return "Grounded answer [policy.txt#file-1:0]"


class FakeIndices:
    def __init__(self):
        self.created = {}

    def exists(self, _index):
        return _index in self.created

    def create(self, index, body):
        self.created[index] = body


class FakeOpenSearch:
    def __init__(self):
        self.indices = FakeIndices()


def load_app_with_temp_data():
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["DATA_DIR"] = temp_dir.name
    os.environ["CHUNK_SIZE"] = "10"
    os.environ["CHUNK_OVERLAP"] = "2"
    os.environ["MAX_UPLOAD_BYTES"] = "64"
    module = importlib.import_module("app")
    return module, temp_dir


def assert_raises_http(status_code, fn, *args):
    try:
        fn(*args)
    except HTTPException as e:
        assert e.status_code == status_code
        return
    raise AssertionError(f"expected HTTPException {status_code}")


async def assert_raises_http_async(status_code, fn, *args):
    try:
        await fn(*args)
    except HTTPException as e:
        assert e.status_code == status_code
        return
    raise AssertionError(f"expected HTTPException {status_code}")


def test_text_helpers(kb):
    assert kb.clean_text(" a\t b \n\n\n c\x00 ") == "a b \n\n c"
    assert kb.split_chunks("abcdefghijXYZ", 5, 2) == ["abcde", "defgh", "ghijX", "jXYZ"]
    assert kb.split_chunks("   ", 5, 2) == []
    assert kb.content_preview("abcdef", 3) == "abc..."

    try:
        kb.split_chunks("abc", 3, 3)
    except ValueError as e:
        assert "overlap" in str(e)
    else:
        raise AssertionError("expected invalid overlap to fail")

    config = kb.runtime_config()
    assert config["hybridRrfK"] == kb.HYBRID_RRF_K
    assert config["graphRrfWeight"] == kb.GRAPH_RRF_WEIGHT


def test_extract_text(kb, temp_dir):
    text_path = Path(temp_dir.name) / "demo.txt"
    text_path.write_text("hello\nworld", encoding="utf-8")
    assert kb.extract_text(text_path) == "hello\nworld"

    unsupported_path = Path(temp_dir.name) / "demo.exe"
    unsupported_path.write_bytes(b"not text")
    assert_raises_http(400, kb.extract_text, unsupported_path)


def test_vector_helpers(kb):
    client = FakeOpenSearch()
    kb.create_vector_index_if_needed(client)
    mapping = client.indices.created[kb.VECTOR_INDEX_NAME]
    assert mapping["settings"]["index"]["knn"] is True
    assert mapping["mappings"]["properties"]["contentVector"]["dimension"] == kb.EMBEDDING_DIMENSION

    provider = FakeEmbeddingProvider(kb.EMBEDDING_DIMENSION)
    kb.embedding_provider = provider
    assert kb.embed_texts(["semantic query"]) == [[0.0] * kb.EMBEDDING_DIMENSION]
    assert provider.requests == [["semantic query"]]

    kb.embedding_provider = FakeEmbeddingProvider(kb.EMBEDDING_DIMENSION - 1)
    assert_raises_http(500, kb.embed_texts, ["wrong dimension"])


def test_graph_helpers(kb):
    client = FakeOpenSearch()
    kb.create_graph_index_if_needed(client)
    mapping = client.indices.created[kb.GRAPH_INDEX_NAME]
    assert mapping["mappings"]["properties"]["relation"]["type"] == "keyword"

    chunks = [
        {"fileId": "procurement", "filename": "procurement.txt", "chunkId": "procurement:0", "chunkIndex": 0, "content": "采购申请需要部门负责人审批。"},
        {"fileId": "reimbursement", "filename": "reimbursement.txt", "chunkId": "reimbursement:0", "chunkIndex": 0, "content": "报销需要关联采购申请。"},
        {"fileId": "remote", "filename": "remote.txt", "chunkId": "remote:0", "chunkIndex": 0, "content": "远程访问必须使用VPN。"},
    ]
    edges = kb.build_graph_records(chunks)
    assert any(edge["relation"] == "CONTAINS" for edge in edges)
    assert any(edge["relation"] == "MENTIONS" and edge["entity"] == "采购申请" for edge in edges)
    assert kb.is_relationship_query("报销为什么需要关联采购申请？")
    assert not kb.is_relationship_query("远程访问安全措施是什么？")
    seed_edges = [
        {"_source": {"entity": "关联采购"}},
        {"_source": {"entity": "采购申请"}},
    ]
    assert kb.filter_graph_seed_edges_by_query("报销为什么需要关联采购申请？", seed_edges) == [seed_edges[1]]

    def hit(chunk_id):
        return {"_id": chunk_id, "_source": {"chunkId": chunk_id}}

    relation_route = kb.graph_route_decision(
        "报销为什么需要关联采购申请？", [hit("text-1")], [hit("vector-1")], {"status": "ANSWER"}
    )
    assert relation_route["routed"] is True
    assert relation_route["reason"] == "relationship_query_cue"
    disagreement_route = kb.graph_route_decision(
        "采购申请", [hit("text-1")], [hit("vector-1")], {"status": "ANSWER"}
    )
    assert disagreement_route["reason"] == "candidate_disagreement"
    agreement_route = kb.graph_route_decision(
        "采购申请", [hit("shared")], [hit("shared")], {"status": "ANSWER"}
    )
    assert agreement_route["reason"] == "candidate_agreement"


def test_hybrid_fusion(kb):
    def hit(chunk_id, score):
        return {
            "_id": chunk_id,
            "_score": score,
            "_source": {"chunkId": chunk_id, "content": f"content for {chunk_id}"},
        }

    fused = kb.fuse_ranked_hits(
        [hit("text-only", 10.0), hit("shared", 9.0)],
        [hit("shared", 0.8), hit("vector-only", 0.7)],
        top_k=2,
    )
    assert [candidate["hit"]["_source"]["chunkId"] for candidate in fused] == ["shared", "text-only"]
    assert fused[0]["textRank"] == 2
    assert fused[0]["vectorRank"] == 1
    assert fused[0]["fusionScore"] > fused[1]["fusionScore"]
    graph_fused = kb.fuse_ranked_hits([], [], top_k=1, graph_hits=[hit("graph-only", 1.0)])
    assert graph_fused[0]["graphRank"] == 1
    protected_direct = kb.fuse_ranked_hits(
        [hit("direct", 10.0)], [], top_k=1, graph_hits=[hit("direct", 1.0)]
    )
    assert protected_direct[0]["fusionScore"] == 1.0 / (kb.HYBRID_RRF_K + 1)


def test_answer_decision(kb):
    weak_hybrid_result = [{"textScore": kb.NO_ANSWER_MIN_TEXT_SCORE - 0.1}]
    weak_decision = kb.decide_answer("HYBRID", weak_hybrid_result)
    assert weak_decision["status"] == "NO_ANSWER"
    assert weak_decision["reason"] == "insufficient_lexical_evidence"
    assert weak_decision["evidence"]["supportingChunkCount"] == 0

    strong_hybrid_result = [{"textScore": kb.NO_ANSWER_MIN_TEXT_SCORE, "vectorScore": 0.4}]
    strong_decision = kb.decide_answer("HYBRID", strong_hybrid_result)
    assert strong_decision["status"] == "ANSWER"
    assert strong_decision["evidence"]["supportingChunkCount"] == 1

    assert kb.decide_answer("HYBRID", [])["status"] == "NO_ANSWER"
    assert kb.decide_answer("VECTOR", [{"vectorScore": 0.4}])["status"] == "ANSWER"


def test_grounded_answer_composer(kb):
    retrieval = {
        "decision": "ANSWER",
        "results": [{
            "fileId": "file-1",
            "filename": "policy.txt",
            "chunkId": "file-1:0",
            "chunkIndex": 0,
            "content": "Procurement requires an approved request.",
            "contentPreview": "Procurement requires an approved request.",
        }],
    }
    generator = FakeAnswerGenerator()
    answer = kb.compose_grounded_answer("What is required?", retrieval, generator)
    assert answer["answerMode"] == "LLM"
    assert answer["citations"][0]["filename"] == "policy.txt"
    assert generator.calls[0][0] == "What is required?"
    assert "policy.txt#file-1:0" in generator.calls[0][1]

    fallback = kb.compose_grounded_answer("What is required?", retrieval)
    assert fallback["answerMode"] == "EXTRACTIVE"
    assert fallback["answer"].startswith("[1] Procurement requires")
    assert fallback["answerReason"].endswith("compact_supporting_evidence")

    no_answer = kb.compose_grounded_answer("Unknown", {"decision": "NO_ANSWER", "results": []}, generator)
    assert no_answer["answerMode"] == "NO_ANSWER"
    assert not generator.calls[1:]


def test_answer_evidence_selection(kb):
    current = {
        "rank": 8,
        "filename": "procurement_policy_2026.txt",
        "chunkId": "current:0",
        "textScore": 10.0,
        "fusionScore": 0.02,
        "content": "2026 年政策已经生效，当前采购必须关联合同。",
        "contentPreview": "2026 年政策已经生效，当前采购必须关联合同。",
    }
    archived = {
        "rank": 1,
        "filename": "procurement_archive_2024.txt",
        "chunkId": "archive:0",
        "textScore": 30.0,
        "fusionScore": 0.04,
        "content": "2024 年历史归档，旧规则已废止。",
        "contentPreview": "2024 年历史归档，旧规则已废止。",
    }
    selected, strategy = kb.select_answer_evidence("历史归档旧规则现在还能用吗？", [archived, current])
    assert strategy == "version_conflict_current_first"
    assert [result["chunkId"] for result in selected] == ["current:0", "archive:0"]

    selected, strategy = kb.select_answer_evidence("当前采购需要什么？", [archived, current])
    assert strategy == "compact_supporting_evidence"
    assert [result["chunkId"] for result in selected] == ["current:0"]

    multi = {
        "rank": 2,
        "filename": "retention_policy.txt",
        "chunkId": "retention:0",
        "textScore": 9.0,
        "fusionScore": 0.01,
        "content": "复盘记录至少保留五年。",
        "contentPreview": "复盘记录至少保留五年。",
    }
    selected, strategy = kb.select_answer_evidence("变更记录和复盘至少保留多久？", [current, multi])
    assert strategy == "multi_evidence"
    assert [result["chunkId"] for result in selected] == ["current:0", "retention:0"]


def test_feedback_helpers(kb):
    request_id = "request-1"
    response = {
        "decision": "ANSWER",
        "answerMode": "EXTRACTIVE",
        "retrievedCount": 2,
        "citations": [{"citationId": 1}],
        "graphRouted": True,
        "graphRouteReason": "relationship_query_cue",
        "graphCandidateOverlap": 0,
        "retrievalLatencyMs": 12.5,
        "results": [{"chunkId": "file-1:0", "rank": 1, "textRank": 1, "vectorRank": 1, "graphRank": None}],
    }
    kb.record_ask_event(request_id, "采购审批怎么做？", response)
    events = kb.load_ask_events()
    assert events[0]["queryLength"] == len("采购审批怎么做？")
    assert "采购审批" not in json.dumps(events[0], ensure_ascii=False)
    assert kb.request_id_exists(request_id)

    kb.append_ask_event({"eventType": "feedback", "requestId": request_id, "rating": "UP"})
    summary = kb.feedback_summary()
    assert summary["askCount"] == 1
    assert summary["positiveFeedbackCount"] == 1
    assert summary["positiveFeedbackRate"] == 1.0

    kb.append_ask_event({"eventType": "feedback", "requestId": request_id, "rating": "DOWN"})
    review_queue = kb.feedback_review_queue()
    assert review_queue["reviewCount"] == 1
    assert review_queue["items"][0]["reasons"] == ["negative_feedback"]


async def test_upload_and_config(kb):
    uploaded = await kb.upload(FakeUploadFile("../kb.txt", b"hello world"))
    assert uploaded["filename"] == "kb.txt"
    assert uploaded["fileId"]

    meta = json.loads(kb.META_PATH.read_text(encoding="utf-8"))
    assert meta["files"][0]["fileId"] == uploaded["fileId"]
    assert meta["files"][0]["filename"] == "kb.txt"
    assert Path(meta["files"][0]["path"]).exists()

    files = kb.list_files()
    assert files["count"] == 1
    assert files["files"] == [{"fileId": uploaded["fileId"], "filename": "kb.txt"}]

    fixed = await kb.upload(FakeUploadFile("fixture.txt", b"fixture"), fileId="eval-fixture")
    assert fixed["fileId"] == "eval-fixture"
    await assert_raises_http_async(409, kb.upload, FakeUploadFile("again.txt", b"again"), "eval-fixture")
    await assert_raises_http_async(400, kb.upload, FakeUploadFile("bad.txt", b"bad"), "not/a-valid-id")

    await assert_raises_http_async(400, kb.upload, FakeUploadFile("bad.exe", b"content"))
    await assert_raises_http_async(413, kb.upload, FakeUploadFile("large.txt", b"x" * 65))
    assert_raises_http(400, kb.ask, {"q": "test", "graphEnabled": "enabled"})

    cfg_resp = kb.set_index_config({"indexMode": "hybrid"})
    assert cfg_resp["ok"] is True
    assert cfg_resp["config"]["indexMode"] == "HYBRID"
    assert kb.get_index_config()["indexMode"] == "HYBRID"


async def main():
    kb, temp_dir = load_app_with_temp_data()
    try:
        test_text_helpers(kb)
        test_extract_text(kb, temp_dir)
        test_vector_helpers(kb)
        test_graph_helpers(kb)
        test_hybrid_fusion(kb)
        test_answer_decision(kb)
        test_grounded_answer_composer(kb)
        test_answer_evidence_selection(kb)
        test_feedback_helpers(kb)
        await test_upload_and_config(kb)
    finally:
        temp_dir.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
