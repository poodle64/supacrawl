"""MCP server for supacrawl - Model Context Protocol integration.

Install with: pip install supacrawl[mcp]
"""

try:
    import fastmcp  # noqa: F401
except ImportError as e:
    raise ImportError("supacrawl[mcp] extras required. Install with: pip install supacrawl[mcp]") from e
