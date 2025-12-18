"""Guard test to ensure legacy HTML-to-Markdown converter is not used in crawl paths.

This test ensures that html_to_markdown (removed in PR4) and
extract_main_content are not imported or used in the production crawl path
(web_scraper/scrapers/).

The legacy HTML-to-Markdown converter was removed from the crawl path in PR2
and the function was deleted in PR4. This test prevents accidental
reintroduction of the fallback.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_crawl4ai_result_does_not_import_html_to_markdown() -> None:
    """Assert that crawl4ai_result.py does not import html_to_markdown."""
    # Navigate from tests/unit/ to project root, then to web_scraper/scrapers/
    result_file = Path(__file__).parent.parent.parent / "web_scraper" / "scrapers" / "crawl4ai_result.py"
    content = result_file.read_text()
    
    # Parse AST to check imports
    tree = ast.parse(content, filename=str(result_file))
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "content" in node.module:
                for alias in node.names:
                    if alias.name in ("html_to_markdown", "extract_main_content"):
                        msg = (
                            f"{result_file.name} imports {alias.name} from {node.module}. "
                            "This legacy fallback must not be used in the crawl path."
                        )
                        raise AssertionError(msg)


def test_scrapers_module_does_not_import_html_to_markdown() -> None:
    """Assert that no file in web_scraper/scrapers/ imports html_to_markdown or extract_main_content."""
    # Navigate from tests/unit/ to project root, then to web_scraper/scrapers/
    scrapers_dir = Path(__file__).parent.parent.parent / "web_scraper" / "scrapers"
    
    violations: list[str] = []
    
    for py_file in scrapers_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        content = py_file.read_text()
        
        # Check for direct imports
        if "html_to_markdown" in content or "extract_main_content" in content:
            # Parse AST to confirm it's an import (not just a string literal)
            try:
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and "content" in node.module:
                            for alias in node.names:
                                if alias.name in ("html_to_markdown", "extract_main_content"):
                                    violations.append(
                                        f"{py_file.name} imports {alias.name} from {node.module}"
                                    )
            except SyntaxError:
                # If we can't parse, check with simple string search
                # This is less precise but catches obvious violations
                if "from web_scraper.content" in content or "import html_to_markdown" in content:
                    violations.append(f"{py_file.name} may import html_to_markdown or extract_main_content")
    
    if violations:
        msg = (
            "Legacy HTML-to-Markdown converter imports found in scrapers module:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nThese imports must not be used in the production crawl path."
        )
        raise AssertionError(msg)
