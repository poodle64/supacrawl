"""Host-shell vocabularies for SSH-pattern MCP servers.

Compose a :class:`mcp_common.executors.SSHConnection` with one of these
shells when you need file-shaped operations on a remote host.

Two shells ship: :class:`PosixHostShell` for POSIX hosts and
:class:`WindowsHostShell` for Windows hosts running OpenSSH server. Both
satisfy the :class:`HostShell` protocol; consumers type-hint against
the protocol and let dependency injection choose the implementation.

Free path utilities (:func:`posix_path`, :func:`windows_path`) are
exposed for callers that need to construct remote paths without holding
a shell instance.
"""

from .base import HostShell, posix_path, windows_path
from .posix import PosixHostShell
from .windows import WindowsHostShell

__all__ = [
    "HostShell",
    "PosixHostShell",
    "WindowsHostShell",
    "posix_path",
    "windows_path",
]
