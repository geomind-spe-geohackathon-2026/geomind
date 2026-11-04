"""Small PDFs written by hand, for the tests of text extraction."""


def word_by_word_pdf(rows):
    """Return a one-page PDF with a table of ``rows``, each word drawn as its own text object.

    The page flips its y axis and every word and space has its own text matrix, as browser-made
    PDFs do; a plain extraction then puts every word on its own line.
    """
    ops = ["1 0 0 -1 0 792 cm"]
    for row_index, row in enumerate(rows):
        y = 100 + 24 * row_index
        for column, cell in enumerate(row):
            x = 60 + 200 * column
            for word in cell.split():
                ops.append(f"BT /F1 11 Tf 1 0 0 -1 {x} 0 Tm 0 -{y} Td ({word}) Tj ET")
                ops.append(f"BT /F1 11 Tf 1 0 0 -1 {x + 7 * len(word)} 0 Tm 0 -{y} Td ( ) Tj ET")
                x += 7 * len(word) + 4
    stream = "\n".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    return out + b"startxref\n%d\n%%%%EOF\n" % start
