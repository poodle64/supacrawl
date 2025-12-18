"""HTTP server utilities for tests.

This module provides reusable server setup functions for integration and e2e tests.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
from pathlib import Path
from typing import Any

# Fixtures directory is at tests/fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def setup_static_server(tmp_path: Path) -> tuple[str, Any]:
    """
    Set up a local HTTP server for static HTML fixture.
    
    Args:
        tmp_path: Temporary directory path (unused, kept for API compatibility).
        
    Returns:
        Tuple of (base_url, server_instance).
    """
    html_dir = FIXTURES_DIR / "html"
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(html_dir), **kwargs)
    
    # Use port 0 to get a free port
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    
    # Start server in daemon thread (will be cleaned up when process exits)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    
    # Small delay to ensure server is ready
    time.sleep(0.1)
    
    return base_url, httpd

