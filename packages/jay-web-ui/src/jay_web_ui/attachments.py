"""Process uploaded attachments into LLM-ready content.

Images are returned as OpenAI-format image_url blocks (base64 data URLs).
Text/code/markdown files are read and inlined as fenced text.
PDFs use PyPDF2 / pdfplumber if available, otherwise produce a hint.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Common image MIME types and corresponding extensions accepted directly
IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Text/code extensions that we treat as readable text
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".md", ".markdown", ".txt", ".rst", ".log",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".csv", ".tsv", ".xml", ".svg",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat",
    ".sql", ".graphql", ".proto",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".lua", ".dart", ".scala", ".clj", ".ex", ".exs",
    ".vue", ".svelte", ".astro",
    ".editorconfig",
    ".dockerfile", "dockerfile",
}

# Filenames that look like text but commonly contain secrets — refuse to inline
# their contents into the LLM payload even if the user uploaded them on purpose.
SENSITIVE_FILENAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    ".gitignore", ".dockerignore",
    "credentials.json", "service-account.json",
    "id_rsa", "id_ed25519", "id_ecdsa",
    ".npmrc", ".pypirc", ".netrc",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")

MAX_TEXT_BYTES = 200_000  # cap text inlining at ~200KB per file
MAX_IMAGE_BYTES = 20_000_000  # 20MB per image


def _is_image(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.lower() in IMAGE_MIME_TYPES:
        return True
    ext = Path(filename).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def _is_text(filename: str, content_type: str | None) -> bool:
    name = filename.lower()
    if Path(name).suffix in TEXT_EXTENSIONS:
        return True
    if name in TEXT_EXTENSIONS:  # e.g. "dockerfile"
        return True
    if content_type and content_type.startswith("text/"):
        return True
    if content_type in {"application/json", "application/xml", "application/x-yaml"}:
        return True
    return False


def _is_pdf(filename: str, content_type: str | None) -> bool:
    if content_type == "application/pdf":
        return True
    return Path(filename).suffix.lower() == ".pdf"


def _build_image_block(file_path: Path, content_type: str | None) -> dict[str, Any] | None:
    try:
        data = file_path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        return None

    media_type = content_type
    if not media_type or media_type not in IMAGE_MIME_TYPES:
        guessed, _ = mimetypes.guess_type(str(file_path))
        media_type = guessed or "image/png"
    # Normalize jpg → jpeg
    if media_type == "image/jpg":
        media_type = "image/jpeg"

    b64 = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64}"},
    }


def _read_text_file(file_path: Path) -> str | None:
    try:
        data = file_path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_TEXT_BYTES:
        data = data[:MAX_TEXT_BYTES]
        suffix = "\n\n[... 文件已截断 ...]"
    else:
        suffix = ""
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return data.decode(encoding) + suffix
        except UnicodeDecodeError:
            continue
    return None


def _extract_pdf_text(file_path: Path) -> str | None:
    """Try pdfplumber, then PyPDF2. Return None if neither is available."""
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(file_path)) as pdf:
            chunks = []
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                chunks.append(f"--- Page {i} ---\n{text}")
            return "\n\n".join(chunks)
    except ImportError:
        pass
    except Exception:
        return None

    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(file_path))
        chunks = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            chunks.append(f"--- Page {i} ---\n{text}")
        return "\n\n".join(chunks)
    except ImportError:
        return None
    except Exception:
        return None


MAX_PDF_PAGES_AS_IMAGES = 20


def _render_pdf_pages_as_images(file_path: Path) -> list[dict[str, Any]]:
    """Render PDF pages to PNG image blocks using pymupdf (fitz).

    Used as fallback when text extraction yields empty content (scanned/image PDFs).
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        return []

    blocks: list[dict[str, Any]] = []
    try:
        doc = fitz.open(str(file_path))
        page_count = min(len(doc), MAX_PDF_PAGES_AS_IMAGES)
        for i in range(page_count):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            png_data = pix.tobytes("png")
            if len(png_data) > MAX_IMAGE_BYTES:
                pix = page.get_pixmap(dpi=100)
                png_data = pix.tobytes("png")
            b64 = base64.b64encode(png_data).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        doc.close()
    except Exception:
        logger.exception("PDF-to-image rendering failed; returning what we have so far")
    return blocks


def _is_pdf_text_empty(text: str | None) -> bool:
    """Check if extracted PDF text is effectively empty."""
    if not text:
        return True
    import re
    stripped = re.sub(r"---\s*Page\s*\d+\s*---", "", text).strip()
    return len(stripped) < 20


def _extract_docx_text(file_path: Path) -> str | None:
    try:
        import docx  # type: ignore

        document = docx.Document(str(file_path))
        return "\n".join(p.text for p in document.paragraphs)
    except ImportError:
        return None
    except Exception:
        return None


def process_attachments(
    files: list[dict[str, Any]],
    workspace: Path,
) -> tuple[list[dict[str, Any]], str]:
    """Convert uploaded attachments into LLM-ready blocks and inlined text.

    Args:
        files: list of {filename, path (relative or absolute), type, size}
        workspace: workspace root used to resolve relative paths

    Returns:
        (image_blocks, text_content)
        - image_blocks: list of OpenAI-style content blocks (image_url)
        - text_content: aggregated text extracted from non-image attachments
    """
    image_blocks: list[dict[str, Any]] = []
    text_chunks: list[str] = []

    for f in files or []:
        filename = f.get("filename") or "unnamed"
        rel_or_abs = f.get("path") or filename
        content_type = (f.get("type") or "").lower() or None

        # Refuse to inline files whose name suggests they hold secrets — the
        # uploader can still keep the file in .uploads/, but its contents are
        # never sent to the LLM as text.
        lower_name = Path(filename).name.lower()
        if (
            lower_name in SENSITIVE_FILENAMES
            or lower_name.endswith(SENSITIVE_SUFFIXES)
        ):
            text_chunks.append(
                f"[已拒绝读取疑似敏感文件: {filename}。如果确认需要分析，"
                "请手动复制内容到对话框，避免凭证误投到 LLM。]"
            )
            continue

        path_obj = Path(rel_or_abs)
        if not path_obj.is_absolute():
            path_obj = workspace / path_obj
        if not path_obj.is_file():
            text_chunks.append(f"[附件缺失: {filename} → {rel_or_abs}]")
            continue

        if _is_image(filename, content_type):
            block = _build_image_block(path_obj, content_type)
            if block:
                image_blocks.append(block)
            else:
                text_chunks.append(f"[图片读取失败或过大: {filename}]")
            continue

        if _is_pdf(filename, content_type):
            text = _extract_pdf_text(path_obj)
            if text is None:
                # No PDF library available — try rendering as images
                page_blocks = _render_pdf_pages_as_images(path_obj)
                if page_blocks:
                    image_blocks.extend(page_blocks)
                else:
                    text_chunks.append(
                        f"[PDF 文件 {filename} 无法解析。请安装 pymupdf: "
                        f"`pip install pymupdf`]"
                    )
            elif _is_pdf_text_empty(text):
                # Image-based/scanned PDF — render pages as images
                page_blocks = _render_pdf_pages_as_images(path_obj)
                if page_blocks:
                    image_blocks.extend(page_blocks)
                else:
                    text_chunks.append(
                        f"[图片型 PDF {filename}，文本提取为空。请安装 pymupdf 以渲染页面: "
                        f"`pip install pymupdf`]"
                    )
            else:
                text_chunks.append(f"--- 附件: {filename} (PDF) ---\n{text}")
            continue

        if filename.lower().endswith(".docx"):
            text = _extract_docx_text(path_obj)
            if text is None:
                text_chunks.append(
                    f"[Word 文件 {filename} 无法解析。请安装 python-docx: "
                    f"`pip install python-docx`]"
                )
            else:
                text_chunks.append(f"--- 附件: {filename} (DOCX) ---\n{text}")
            continue

        if _is_text(filename, content_type):
            text = _read_text_file(path_obj)
            if text is None:
                text_chunks.append(f"[文本文件读取失败: {filename}]")
            else:
                lang = Path(filename).suffix.lstrip(".") or ""
                text_chunks.append(
                    f"--- 附件: {filename} ---\n```{lang}\n{text}\n```"
                )
            continue

        text_chunks.append(
            f"[二进制附件未解析: {filename} ({content_type or 'unknown'}, "
            f"{f.get('size', '?')} bytes)。已保存到 {rel_or_abs}]"
        )

    text_content = "\n\n".join(text_chunks)
    return image_blocks, text_content


def build_multimodal_content(
    user_message: str,
    image_blocks: list[dict[str, Any]],
    text_attachments: str,
) -> str | list[dict[str, Any]]:
    """Combine user text + extracted attachment text + image blocks into LLM content.

    Returns either a plain string (no images) or a list of OpenAI content blocks.
    """
    full_text = user_message or ""
    if text_attachments:
        if full_text:
            full_text = f"{full_text}\n\n{text_attachments}"
        else:
            full_text = text_attachments

    if not image_blocks:
        return full_text

    blocks: list[dict[str, Any]] = []
    if full_text:
        blocks.append({"type": "text", "text": full_text})
    blocks.extend(image_blocks)
    return blocks
