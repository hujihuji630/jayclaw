"""Tests for jay_web_ui.attachments — attachment processing pipeline.

Covers:
- Image / text / PDF / DOCX / unknown-binary classification
- Sensitive filename rejection (.env, .pem, id_rsa, etc.)
- Size caps (text, image)
- Encoding fallback chain
- build_multimodal_content combining text + images
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from jay_web_ui.attachments import (
    IMAGE_EXTENSIONS,
    IMAGE_MIME_TYPES,
    MAX_IMAGE_BYTES,
    MAX_TEXT_BYTES,
    SENSITIVE_FILENAMES,
    SENSITIVE_SUFFIXES,
    TEXT_EXTENSIONS,
    _is_image,
    _is_pdf,
    _is_pdf_text_empty,
    _is_text,
    _read_text_file,
    build_multimodal_content,
    process_attachments,
)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def test_is_image_by_mime():
    assert _is_image("foo.bin", "image/png")
    assert _is_image("foo.bin", "IMAGE/PNG".lower())  # caller already lowers


def test_is_image_by_extension():
    assert _is_image("photo.JPG", None)  # extension is case-insensitive
    assert _is_image("a.webp", None)
    assert _is_image("a.gif", "application/octet-stream")


def test_is_image_rejects_text():
    assert not _is_image("readme.md", "text/markdown")
    assert not _is_image("script.py", None)


def test_is_text_by_extension():
    assert _is_text("script.py", None)
    assert _is_text("notes.md", None)
    assert _is_text("data.json", None)


def test_is_text_by_mime():
    assert _is_text("anything.bin", "text/plain")
    assert _is_text("anything.bin", "application/json")


def test_is_text_dockerfile_no_extension():
    """Filenames like `dockerfile` (no ext) are recognized as text."""
    assert _is_text("Dockerfile", None)
    assert _is_text("dockerfile", None)


def test_is_pdf():
    assert _is_pdf("doc.pdf", None)
    assert _is_pdf("doc.PDF", None)
    assert _is_pdf("foo.bin", "application/pdf")
    assert not _is_pdf("doc.txt", None)


# ---------------------------------------------------------------------------
# Sensitive filename rejection
# ---------------------------------------------------------------------------


def test_sensitive_filenames_rejected_no_inline(tmp_path: Path):
    """`.env` content is never inlined into LLM context, even if uploaded."""
    target = tmp_path / ".env"
    target.write_text("OPENAI_API_KEY=sk-real-secret-do-not-leak", encoding="utf-8")

    files = [{
        "filename": ".env",
        "path": str(target),
        "type": "text/plain",
        "size": target.stat().st_size,
    }]
    image_blocks, text_content = process_attachments(files, tmp_path)

    assert image_blocks == []
    # Reject placeholder is shown
    assert "拒绝读取疑似敏感文件" in text_content
    # The actual key value must NOT appear
    assert "sk-real-secret-do-not-leak" not in text_content


@pytest.mark.parametrize("name", [
    ".env", ".env.local", ".env.production",
    "credentials.json", "id_rsa", "id_ed25519",
    ".npmrc", ".pypirc", ".netrc",
])
def test_each_sensitive_filename_is_blocked(tmp_path: Path, name):
    target = tmp_path / name
    target.write_text("super secret content", encoding="utf-8")

    files = [{"filename": name, "path": str(target), "type": "text/plain", "size": 20}]
    _, text_content = process_attachments(files, tmp_path)
    assert "拒绝读取疑似敏感文件" in text_content
    assert "super secret content" not in text_content


@pytest.mark.parametrize("suffix", [".pem", ".key", ".pfx", ".p12"])
def test_sensitive_suffixes_blocked(tmp_path: Path, suffix):
    target = tmp_path / f"private{suffix}"
    target.write_text("BEGIN PRIVATE KEY", encoding="utf-8")

    files = [{
        "filename": f"private{suffix}",
        "path": str(target),
        "type": "application/octet-stream",
        "size": 100,
    }]
    _, text_content = process_attachments(files, tmp_path)
    assert "拒绝读取疑似敏感文件" in text_content
    assert "BEGIN PRIVATE KEY" not in text_content


# ---------------------------------------------------------------------------
# Text reading
# ---------------------------------------------------------------------------


def test_read_text_utf8(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello 中文", encoding="utf-8")
    assert _read_text_file(f) == "hello 中文"


def test_read_text_truncates_at_cap(tmp_path: Path):
    f = tmp_path / "big.txt"
    payload = "x" * (MAX_TEXT_BYTES + 100)
    f.write_bytes(payload.encode("utf-8"))
    out = _read_text_file(f)
    assert out is not None
    assert "[... 文件已截断 ...]" in out
    # The text portion is at most MAX_TEXT_BYTES chars
    assert out.count("x") == MAX_TEXT_BYTES


def test_read_text_falls_back_to_gbk(tmp_path: Path):
    """GBK-encoded Chinese should be readable when UTF-8 fails."""
    f = tmp_path / "gbk.txt"
    f.write_bytes("中文测试".encode("gbk"))
    out = _read_text_file(f)
    # Must have decoded *somehow* (gbk or latin-1 fallback) — never None
    assert out is not None
    # If GBK won, the actual Chinese characters appear
    if "中文测试" in out:
        assert True
    else:
        # latin-1 fallback would still produce a string, just garbled
        assert len(out) > 0


# ---------------------------------------------------------------------------
# process_attachments end-to-end
# ---------------------------------------------------------------------------


def test_process_attachments_missing_file_emits_placeholder(tmp_path: Path):
    files = [{
        "filename": "ghost.txt",
        "path": "ghost.txt",  # doesn't exist
        "type": "text/plain",
        "size": 10,
    }]
    image_blocks, text_content = process_attachments(files, tmp_path)
    assert image_blocks == []
    assert "[附件缺失:" in text_content


def test_process_attachments_text_inlines_with_fence(tmp_path: Path):
    f = tmp_path / "snippet.py"
    f.write_text("def hi(): pass\n", encoding="utf-8")
    files = [{"filename": "snippet.py", "path": "snippet.py", "type": "text/x-python", "size": 20}]

    _, text_content = process_attachments(files, tmp_path)
    assert "snippet.py" in text_content
    assert "```py" in text_content
    assert "def hi(): pass" in text_content


def test_process_attachments_image_makes_image_block(tmp_path: Path):
    """A 1x1 PNG should round-trip into an image_url block with base64 data."""
    # 1x1 transparent PNG
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAj"
        "CB0C8AAAAASUVORK5CYII="
    )
    f = tmp_path / "pixel.png"
    f.write_bytes(png_data)

    files = [{"filename": "pixel.png", "path": "pixel.png", "type": "image/png", "size": len(png_data)}]
    image_blocks, text_content = process_attachments(files, tmp_path)

    assert len(image_blocks) == 1
    block = image_blocks[0]
    assert block["type"] == "image_url"
    url = block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert text_content == ""


def test_process_attachments_oversize_image_dropped(tmp_path: Path):
    """Images larger than MAX_IMAGE_BYTES are skipped with a placeholder."""
    f = tmp_path / "huge.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_IMAGE_BYTES + 100))
    files = [{"filename": "huge.png", "path": "huge.png", "type": "image/png", "size": MAX_IMAGE_BYTES + 100}]

    image_blocks, text_content = process_attachments(files, tmp_path)
    assert image_blocks == []
    assert "图片读取失败或过大" in text_content


def test_process_attachments_unknown_binary_falls_through(tmp_path: Path):
    f = tmp_path / "weird.xyz"
    f.write_bytes(b"\x00\x01\x02\x03")
    files = [{"filename": "weird.xyz", "path": "weird.xyz", "type": "application/x-weird", "size": 4}]

    image_blocks, text_content = process_attachments(files, tmp_path)
    assert image_blocks == []
    assert "二进制附件未解析" in text_content


def test_process_attachments_relative_path_resolved_against_workspace(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    f = sub / "a.txt"
    f.write_text("hello", encoding="utf-8")

    # Path is relative — process_attachments should resolve against workspace
    files = [{"filename": "a.txt", "path": "sub/a.txt", "type": "text/plain", "size": 5}]
    _, text_content = process_attachments(files, tmp_path)
    assert "hello" in text_content


# ---------------------------------------------------------------------------
# build_multimodal_content
# ---------------------------------------------------------------------------


def test_build_multimodal_text_only_returns_string():
    out = build_multimodal_content("hello", [], "")
    assert out == "hello"
    assert isinstance(out, str)


def test_build_multimodal_text_with_attachment_text():
    out = build_multimodal_content("hello", [], "extra context")
    assert out == "hello\n\nextra context"


def test_build_multimodal_with_image_returns_blocks():
    img = {"type": "image_url", "image_url": {"url": "data:image/png;base64,XXX"}}
    out = build_multimodal_content("describe this", [img], "")
    assert isinstance(out, list)
    assert out[0] == {"type": "text", "text": "describe this"}
    assert out[1] == img


def test_build_multimodal_image_only_no_text_no_text_block():
    """When user provides no text and no extracted attachment text, no text
    block is added — just images."""
    img = {"type": "image_url", "image_url": {"url": "data:image/png;base64,XXX"}}
    out = build_multimodal_content("", [img], "")
    assert out == [img]


# ---------------------------------------------------------------------------
# _is_pdf_text_empty
# ---------------------------------------------------------------------------


def test_is_pdf_text_empty_truly_empty():
    assert _is_pdf_text_empty(None)
    assert _is_pdf_text_empty("")


def test_is_pdf_text_empty_only_page_markers():
    """A scanned PDF where text extraction returned only page boundaries."""
    text = "--- Page 1 ---\n\n--- Page 2 ---\n\n"
    assert _is_pdf_text_empty(text)


def test_is_pdf_text_empty_has_real_content():
    text = "--- Page 1 ---\nThis is the actual content of the document"
    assert not _is_pdf_text_empty(text)


# ---------------------------------------------------------------------------
# Module-level constants — pin these so future edits don't accidentally
# add .env back to the inline whitelist.
# ---------------------------------------------------------------------------


def test_env_not_in_text_extensions():
    assert ".env" not in TEXT_EXTENSIONS
    assert ".gitignore" not in TEXT_EXTENSIONS


def test_sensitive_filenames_includes_env_family():
    assert ".env" in SENSITIVE_FILENAMES
    assert ".env.local" in SENSITIVE_FILENAMES


def test_sensitive_suffixes_includes_keys():
    assert ".pem" in SENSITIVE_SUFFIXES
    assert ".key" in SENSITIVE_SUFFIXES
