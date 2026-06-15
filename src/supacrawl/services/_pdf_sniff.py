"""Low-level PDF detection primitives shared by http_fetch and pdf modules.

Kept separate so a fetch primitive (http_fetch) can consult PDF size and magic
limits without importing from the application-layer pdf module, avoiding
awkward layering while preserving a single source of truth for each constant.
"""

# Magic bytes that every PDF file starts with.
PDF_MAGIC = b"%PDF"

# How many leading bytes to inspect for the magic marker.
PDF_SNIFF_SIZE = 1024

# Maximum PDF file size in bytes (50 MB). Prevents memory exhaustion on huge files.
MAX_PDF_SIZE = 50 * 1024 * 1024


def is_pdf_bytes(data: bytes) -> bool:
    """Return True if *data* starts with the ``%PDF`` magic marker."""
    return PDF_MAGIC in data[:PDF_SNIFF_SIZE]
