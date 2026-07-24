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


def test_extract_text(kb, temp_dir):
    text_path = Path(temp_dir.name) / "demo.txt"
    text_path.write_text("hello\nworld", encoding="utf-8")
    assert kb.extract_text(text_path) == "hello\nworld"

    unsupported_path = Path(temp_dir.name) / "demo.exe"
    unsupported_path.write_bytes(b"not text")
    assert_raises_http(400, kb.extract_text, unsupported_path)


async def test_upload_and_config(kb):
    uploaded = await kb.upload(FakeUploadFile("../kb.txt", b"hello world"))
    assert uploaded["filename"] == "kb.txt"
    assert uploaded["fileId"]

    meta = json.loads(kb.META_PATH.read_text(encoding="utf-8"))
    assert meta["files"][0]["fileId"] == uploaded["fileId"]
    assert meta["files"][0]["filename"] == "kb.txt"
    assert Path(meta["files"][0]["path"]).exists()

    await assert_raises_http_async(400, kb.upload, FakeUploadFile("bad.exe", b"content"))
    await assert_raises_http_async(413, kb.upload, FakeUploadFile("large.txt", b"x" * 65))

    cfg_resp = kb.set_index_config({"indexMode": "hybrid"})
    assert cfg_resp["ok"] is True
    assert cfg_resp["config"]["indexMode"] == "HYBRID"
    assert kb.get_index_config()["indexMode"] == "HYBRID"


async def main():
    kb, temp_dir = load_app_with_temp_data()
    try:
        test_text_helpers(kb)
        test_extract_text(kb, temp_dir)
        await test_upload_and_config(kb)
    finally:
        temp_dir.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
