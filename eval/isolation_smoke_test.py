#!/usr/bin/env python3
"""Smoke test the evaluation-corpus isolation contract without an API."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_retrieval_eval as evaluator


def main() -> None:
    corpus = evaluator.load_corpus_manifest(evaluator.DEFAULT_CORPUS_MANIFEST, evaluator.DEFAULT_FIXTURE_DIR)
    original_request_json = evaluator.request_json
    original_upload_file = evaluator.upload_file
    try:
        calls = []

        def empty_api(url, method="GET", body=None, headers=None):
            calls.append((url, method))
            if url.endswith("/files"):
                return {"files": []}
            return {"ok": True}

        def deterministic_upload(api_url, path, file_id):
            assert corpus[path.name]["fileId"] == file_id
            return {"fileId": file_id, "filename": path.name}

        evaluator.request_json = empty_api
        evaluator.upload_file = deterministic_upload
        uploaded = evaluator.bootstrap_fixtures("http://example.test", evaluator.DEFAULT_FIXTURE_DIR, corpus, "HYBRID")
        assert uploaded == sorted(corpus)
        assert ("http://example.test/index/rebuild", "POST") in calls

        def contaminated_api(url, method="GET", body=None, headers=None):
            if url.endswith("/files"):
                return {"files": [{"fileId": "user-file", "filename": "private.txt"}]}
            raise AssertionError("a contaminated corpus must not be reindexed")

        evaluator.request_json = contaminated_api
        try:
            evaluator.bootstrap_fixtures("http://example.test", evaluator.DEFAULT_FIXTURE_DIR, corpus, "TEXT")
        except RuntimeError as error:
            assert "not isolated" in str(error)
        else:
            raise AssertionError("expected contaminated corpus rejection")
    finally:
        evaluator.request_json = original_request_json
        evaluator.upload_file = original_upload_file


if __name__ == "__main__":
    main()
