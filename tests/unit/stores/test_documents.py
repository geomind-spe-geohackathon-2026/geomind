"""The text of a document, shared by the project's files and the knowledge base."""

import pytest

from geomind.errors import ToolError
from geomind.stores.documents import document_text


def test_a_text_file_reads_as_it_is_and_a_binary_one_is_refused():
    """UTF-8 reads whole; bytes that are no text are ``not_text``."""
    assert document_text("a.md", "Höhe\n".encode()) == "Höhe\n"
    with pytest.raises(ToolError) as raised:
        document_text("b.bin", b"\x00\x01\xff")
    assert raised.value.code == "not_text"
