"""Quality metrics calculation utilities for tests.

This module provides reusable metric calculation functions extracted from
test_baseline_quality.py to avoid duplication.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web_scraper.models import Page


def calculate_page_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate page count metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with page count metrics.
    """
    unique_urls = len(set(page.url for page in pages))
    return {
        "total_pages": len(pages),
        "unique_urls": unique_urls,
    }


def calculate_content_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate content size metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with content size metrics.
    """
    if not pages:
        return {
            "avg_word_count": 0.0,
            "avg_char_count": 0.0,
        }
    
    word_counts = [len(page.content_markdown.split()) for page in pages]
    char_counts = [len(page.content_markdown) for page in pages]
    
    return {
        "avg_word_count": sum(word_counts) / len(word_counts),
        "avg_char_count": sum(char_counts) / len(char_counts),
    }


def calculate_structure_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate structure metrics (headings, code blocks).
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with structure metrics.
    """
    if not pages:
        return {
            "pages_with_headings": 0,
            "avg_heading_count": 0.0,
            "avg_code_block_count": 0.0,
        }
    
    heading_counts = []
    code_block_counts = []
    pages_with_headings = 0
    
    for page in pages:
        lines = page.content_markdown.splitlines()
        heading_count = sum(1 for line in lines if line.strip().startswith("#"))
        code_block_count = page.content_markdown.count("```") // 2  # Pairs of ```
        
        heading_counts.append(heading_count)
        code_block_counts.append(code_block_count)
        
        if heading_count > 0:
            pages_with_headings += 1
    
    return {
        "pages_with_headings": pages_with_headings,
        "avg_heading_count": sum(heading_counts) / len(heading_counts) if heading_counts else 0.0,
        "avg_code_block_count": sum(code_block_counts) / len(code_block_counts) if code_block_counts else 0.0,
    }


def calculate_link_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate link metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with link metrics.
    """
    if not pages:
        return {
            "avg_link_count": 0.0,
        }
    
    link_counts = [page.content_markdown.count("](") for page in pages]
    
    return {
        "avg_link_count": sum(link_counts) / len(link_counts) if link_counts else 0.0,
    }


def calculate_format_metrics(snapshot_path: Path) -> dict[str, Any]:
    """
    Calculate format metrics from snapshot filesystem.
    
    Args:
        snapshot_path: Path to snapshot root directory.
        
    Returns:
        Dictionary with format metrics.
    """
    manifest_path = snapshot_path / "manifest.json"
    manifest_exists = manifest_path.exists()
    
    manifest_page_count = 0
    if manifest_exists:
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_page_count = manifest_data.get("total_pages", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Count markdown files
    markdown_dir = snapshot_path / "markdown"
    markdown_files_written = 0
    if markdown_dir.exists():
        markdown_files_written = len(list(markdown_dir.rglob("*.md")))
    
    return {
        "markdown_files_written": markdown_files_written,
        "manifest_exists": manifest_exists,
        "manifest_page_count": manifest_page_count,
    }


def calculate_determinism_metric(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate determinism metric (content hash of first page).
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with determinism metric.
    """
    if not pages:
        return {
            "content_hash_first_page": "",
        }
    
    return {
        "content_hash_first_page": pages[0].content_hash,
    }


def calculate_all_metrics(pages: list[Page], snapshot_path: Path) -> dict[str, Any]:
    """
    Calculate all quality metrics for a crawl.
    
    Args:
        pages: List of Page objects from crawl.
        snapshot_path: Path to snapshot root directory.
        
    Returns:
        Dictionary with all quality metrics.
    """
    metrics = {}
    metrics.update(calculate_page_metrics(pages))
    metrics.update(calculate_content_metrics(pages))
    metrics.update(calculate_structure_metrics(pages))
    metrics.update(calculate_link_metrics(pages))
    metrics.update(calculate_format_metrics(snapshot_path))
    metrics.update(calculate_determinism_metric(pages))
    return metrics
