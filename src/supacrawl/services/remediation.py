"""Concrete, honest recovery hints for failed or low-quality scrapes.

These map an observed failure — an error string, or thin extracted content — to a
specific next action the caller (often an autonomous agent) can take, rather than
leaving it to parse a stack trace. Hints are deliberately conservative: when no
action is likely to help, ``remediation_hint`` returns None. That restraint is the
lesson of #107, where a blanket "switch engines" hint sent agents into pointless
retry loops on failures engine-switching could never fix.

Anti-bot failures are intentionally NOT handled here; they keep the
availability-aware stealth hint in ``scrape._stealth_hint`` so the advice reflects
which engines are actually installed.
"""

# (substring, hint) pairs checked in order; the first match wins. Substrings are
# matched against a lowercased error message.
_ERROR_HINTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("timeout", "timed out"),
        "The page did not finish loading in time. Retry with a higher timeout "
        "(e.g. timeout=60000) or a larger wait_for to allow slow or JS-rendered content.",
    ),
    (
        (
            "err_name_not_resolved",
            "getaddrinfo",
            "name or service not known",
            "nodename nor servname",
            "could not resolve",
        ),
        "The host could not be resolved. Check the URL spelling and your network/DNS.",
    ),
    (
        (
            "err_connection_refused",
            "connection refused",
            "err_connection_reset",
            "connection reset",
            "err_connection_closed",
        ),
        "The connection was refused or reset. The server may be down or blocking "
        "automated clients; retry later or via a proxy.",
    ),
    (
        ("err_cert", "ssl", "certificate", "sslv3", "tlsv1"),
        "A TLS/certificate error occurred. The site's certificate may be invalid, expired, or self-signed.",
    ),
    (
        ("404", "not found"),
        "The page was not found (404). Verify the URL is correct and publicly reachable.",
    ),
    (
        ("500", "502", "503", "504", "bad gateway", "gateway timeout", "service unavailable", "internal server error"),
        "The server returned an error (5xx). This is usually transient; retry after a short delay.",
    ),
]


def remediation_hint(error_message: str) -> str | None:
    """Return a concrete recovery hint for a failure message, or None.

    Args:
        error_message: The raw error text (exception string or result error).

    Returns:
        A single-sentence, actionable hint, or None when no specific action is
        likely to help (so callers do not emit speculative advice).
    """
    low = error_message.lower()
    for needles, hint in _ERROR_HINTS:
        if any(needle in low for needle in needles):
            return hint
    return None


def thin_content_hint(only_main_content: bool) -> str:
    """Return a recovery hint for a page that yielded suspiciously little content.

    Args:
        only_main_content: Whether main-content extraction was applied (and may
            therefore have discarded the real content).

    Returns:
        An actionable hint tailored to whether main-content extraction was on.
    """
    if only_main_content:
        return (
            "Try only_main_content=False (--no-only-main-content) to keep more of the page, "
            "or a larger wait_for if the content loads late."
        )
    return "Try a larger wait_for if content loads late, or check whether the page needs JavaScript or authentication."
