"""The text of a document: a PDF page by page, or a UTF-8 file as it is.

The project's files and the knowledge base read their documents alike, so the text comes from
one place.
"""

import io
import re

from geomind.errors import ToolError

PDF_START = b"%PDF-"


def not_text(name, reason):
    """Return the error of a file that gives no text."""
    return ToolError(f"rag_read: {name!r} {reason}", code="not_text", path="name")


def laid_out(text):
    """Return a page's layout text with its runs of spaces shortened and blank lines dropped.

    Layout extraction keeps a table row on one line, as on the page, where plain extraction gives
    a PDF drawn word by word one word per line; the long runs of spaces only cost tokens.
    """
    lines = (re.sub(" {3,}", "  ", line).strip() for line in (text or "").splitlines())
    return "\n".join(line for line in lines if line)


def pdf_text(name, content):
    """Return the text of a PDF, each page after its ``[page n]`` marker, laid out as the page."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise not_text(name, "is an encrypted PDF")
        pages = [laid_out(page.extract_text(extraction_mode="layout")) for page in reader.pages]
    except (PyPdfError, ValueError, KeyError, OSError) as error:
        raise not_text(name, f"is a PDF that cannot be read: {error}") from error
    if not "".join(pages).strip():
        raise not_text(name, "is a PDF with no text layer, such as a scan")
    marked = [f"[page {number}]\n{text}" for number, text in enumerate(pages, start=1)]
    return "\n\n".join(marked)


def plain_text(name, content):
    """Return the text of a UTF-8 file; a binary file is not text."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise not_text(name, "is not UTF-8 text") from error
    if "\x00" in text:
        raise not_text(name, "is a binary file, not text")
    return text


def document_text(name, content):
    """Return the text of a file, by its content."""
    return pdf_text(name, content) if content.startswith(PDF_START) else plain_text(name, content)
