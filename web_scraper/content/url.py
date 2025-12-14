"""URL normalisation and canonical extraction utilities."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


def normalise_url(
    raw_url: str, html: str | None = None, entrypoint: str | None = None
) -> str:
    """
    Normalise URLs for deduping and hashing.

    - Prefer canonical link tags when available.
    - Strip fragments and common tracking parameters (utm_*, fbclid, etc).

    Args:
        raw_url: The URL to normalise.
        html: Optional HTML content to extract canonical URL from.
        entrypoint: Optional entrypoint URL to resolve relative canonicals.

    Returns:
        Normalised URL string.
    """
    cleaned = strip_tracking_params(_strip_fragment(raw_url))
    canonical = extract_canonical_url(html, cleaned, entrypoint=entrypoint)
    return strip_tracking_params(_strip_fragment(canonical))


def _strip_fragment(raw_url: str) -> str:
    """Remove URL fragment (e.g., #section)."""
    parts = urlsplit(raw_url)
    return urlunsplit(parts._replace(fragment=""))


def strip_tracking_params(raw_url: str) -> str:
    """
    Remove common tracking parameters from URL.

    Removes: utm_*, fbclid, gclid, igshid, mc_eid, ref, ref_src.

    Args:
        raw_url: URL to clean.

    Returns:
        URL with tracking parameters removed.
    """
    parsed = urlsplit(raw_url)
    if not parsed.query:
        return raw_url

    params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in {
            "fbclid",
            "gclid",
            "igshid",
            "mc_eid",
            "ref",
            "ref_src",
        }:
            continue
        params.append((key, value))

    cleaned_query = urlencode(params, doseq=True)
    return urlunsplit(parsed._replace(query=cleaned_query))


def extract_canonical_url(
    html: str | None, fallback_url: str, entrypoint: str | None = None
) -> str:
    """
    Extract canonical URL from HTML when available.

    Args:
        html: HTML content to parse.
        fallback_url: URL to return if no canonical found.
        entrypoint: Optional base URL for resolving relative canonicals.

    Returns:
        Canonical URL or fallback.
    """
    if not html:
        return fallback_url

    try:
        soup = BeautifulSoup(html, "html.parser")
        link = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
        if not link or not link.has_attr("href"):
            return fallback_url
        href_attr = link["href"]
        # href can be a list in some cases, take first item
        href: str | None = None
        if isinstance(href_attr, list):
            href = href_attr[0] if href_attr else None
        elif isinstance(href_attr, str):
            href = href_attr
        if not href:
            return fallback_url
        canonical = urljoin(entrypoint or fallback_url, href)
        return canonical
    except Exception:
        return fallback_url

