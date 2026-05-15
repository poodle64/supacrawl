"""Remote-host transport abstractions shared across MCP servers.

Each executor encapsulates a single transport mechanism for talking to a
remote host. Servers compose an executor with a vocabulary layer (see
:mod:`mcp_common.host_shell`) when they need host-shaped operations like
file read/write or directory listing.

Submodules:

- :mod:`mcp_common.executors.adb`: Android Debug Bridge for phones,
  tablets, and sticks.
- :mod:`mcp_common.executors.ssh`: a cached asyncssh connection with
  auto-reconnect, command execution, and SFTP upload.

Import the symbols you need from the submodule directly so unrelated
backends are not pulled in transitively. ``mcp_common.executors.ssh``
requires ``asyncssh``; ``mcp_common.executors.adb`` is stdlib-only.
"""
