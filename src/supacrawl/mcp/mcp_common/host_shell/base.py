"""Host-shell vocabulary.

A :class:`HostShell` describes file-shaped operations on a remote host:
read, write, exists, hash, list. Two implementations ship with
mcp-common: :class:`PosixHostShell` (cat/base64/sha256sum/test/ls) and
:class:`WindowsHostShell` (PowerShell + base64).

Servers compose an :class:`mcp_common.executors.SSHConnection` with one
of these shells when they need to manipulate files on the remote host.
A server that only runs commands (``unbound-control``, ``docker exec``,
``systemctl``) and never touches files can ignore HostShell entirely
and use the bare connection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HostShell(Protocol):
    """File-shaped operations on a remote host.

    Implementations choose a hashing algorithm appropriate to their
    host (e.g. ``sha256`` on POSIX, ``SHA1`` on Windows) when ``algorithm``
    is omitted, but always honour an explicit override.
    """

    async def read_file(self, remote_path: str) -> str:
        """Return the contents of a file on the remote host."""

    async def write_file(self, remote_path: str, content: str, *, mode: str | None = None) -> None:
        """Write ``content`` to ``remote_path``.

        ``mode`` is an optional ``chmod``-style mode string. POSIX shells
        apply it; Windows shells must accept and ignore it.
        """

    async def file_exists(self, remote_path: str) -> bool:
        """Return ``True`` when the path exists on the remote host."""

    async def file_hash(self, remote_path: str, algorithm: str | None = None) -> str:
        """Return a hex digest of the file at ``remote_path``."""

    async def list_directory(self, remote_path: str, *, depth: int = 0) -> list[str]:
        """List items in a remote directory.

        Args:
            remote_path: Directory path on the remote host.
            depth: Recursion depth. ``0`` returns immediate children
                (names only). Non-zero implementations return full
                paths up to the given recursion depth.
        """


def posix_path(*parts: str) -> str:
    """Join path parts with ``/``. Trailing/leading slashes between parts are
    collapsed; an absolute first part is preserved."""
    if not parts:
        return ""
    cleaned: list[str] = []
    for index, part in enumerate(parts):
        if not part:
            continue
        # Preserve leading slash on the first part only
        stripped = part.rstrip("/")
        if index == 0:
            cleaned.append(stripped)
        else:
            cleaned.append(stripped.lstrip("/"))
    return "/".join(p for p in cleaned if p)


def windows_path(*parts: str) -> str:
    """Join path parts with ``\\``. Repeated separators between parts are
    collapsed."""
    if not parts:
        return ""
    cleaned: list[str] = []
    for index, part in enumerate(parts):
        if not part:
            continue
        stripped = part.rstrip("\\")
        if index == 0:
            cleaned.append(stripped)
        else:
            cleaned.append(stripped.lstrip("\\"))
    return "\\".join(p for p in cleaned if p)
