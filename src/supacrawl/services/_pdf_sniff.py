"""Low-level PDF detection primitives shared by http_fetch and pdf modules.

Kept separate so a fetch primitive (http_fetch) can consult PDF size and magic
limits without importing from the application-layer pdf module, avoiding
awkward layering while preserving a single source of truth for each constant.
"""

# PDF file signature including the mandatory hyphen (ISO 32000 §7.5.2).
# Using "%PDF-" rather than bare "%PDF" eliminates false positives from HTML or
# documentation that happens to mention "%PDF" in text — the hyphen is always
# present in real PDF headers ("%PDF-1.x" through "%PDF-2.0") and essentially
# never appears in non-PDF content.
PDF_MAGIC = b"%PDF-"

# How many leading bytes to inspect for the magic marker.
# ISO 32000 §7.5.2 requires the header at byte 0, but Acrobat tolerates it
# within the first 1024 bytes to accommodate leading BOMs or junk bytes that
# some real-world PDF generators prepend.  A window is strictly preferable to
# startswith(offset=0) because a false negative (missing a valid PDF) is worse
# than a false positive (non-PDF with the signature buried deep) for a scraper.
PDF_SNIFF_SIZE = 1024

# Maximum PDF file size in bytes (50 MB). Prevents memory exhaustion on huge files.
MAX_PDF_SIZE = 50 * 1024 * 1024


def is_pdf_bytes(data: bytes) -> bool:
    """Return True if *data* contains the ``%PDF-`` signature within the first 1024 bytes.

    This function is only called on responses already suspected to be binary
    (Content-Type ``application/octet-stream`` or absent); ``text/html``
    responses are filtered out in ``http_fetch.fetch_static`` before the sniff
    is reached, so normal web pages never pass through here.

    The ``%PDF-`` signature (mandatory hyphen, ISO 32000 §7.5.2) avoids
    matching prose that merely contains the substring ``%PDF`` — real PDF
    headers always include the version suffix (``%PDF-1.x`` through
    ``%PDF-2.0``), which the hyphen anchors.

    The 1024-byte search window matches Acrobat's documented tolerance for a
    header that is not exactly at byte 0 (BOM/leading junk from some
    generators).  A false negative — rejecting a valid PDF whose header falls
    within the first 1024 bytes — is the worse error for a scraper, because
    it silently skips parseable content.  On the narrow residual false
    positive (binary-suspected body that happens to contain ``%PDF-`` within
    1024 bytes), the PDF parser raises ``ValueError`` loudly rather than
    returning corrupt output.
    """
    return PDF_MAGIC in data[:PDF_SNIFF_SIZE]
