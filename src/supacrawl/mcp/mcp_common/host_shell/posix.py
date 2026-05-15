"""POSIX host-shell implementation.

File operations expressed as POSIX shell commands (``cat``, ``base64``,
``test``, ``ls``, ``sha256sum`` and friends) executed over a shared
:class:`mcp_common.executors.SSHConnection`. Suitable for any POSIX
remote: Linux, BSD, macOS, embedded devices with a busybox-equivalent
shell.
"""

from __future__ import annotations

import base64
import shlex

from ..executors.ssh import SSHConnection, SSHError


class PosixHostShell:
    """File operations on a POSIX remote host.

    Constructed with a :class:`SSHConnection`; does not own the
    connection's lifecycle. Several shells may share one connection.

    Implements the :class:`HostShell` protocol structurally; explicit
    inheritance is unnecessary.
    """

    _HASH_BINARIES = {"sha256": "sha256sum", "sha1": "sha1sum", "md5": "md5sum"}
    DEFAULT_HASH = "sha256"

    def __init__(self, connection: SSHConnection) -> None:
        self._conn = connection

    async def read_file(self, remote_path: str) -> str:
        """Read a file via ``cat``."""
        result = await self._conn.run(f"cat {shlex.quote(remote_path)}")
        if not result.ok:
            raise SSHError(f"read_file({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        return result.stdout

    async def write_file(self, remote_path: str, content: str, *, mode: str | None = None) -> None:
        """Write a file via ``base64 -d`` to sidestep quoting issues."""
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        quoted_path = shlex.quote(remote_path)
        cmd = f"echo {shlex.quote(encoded)} | base64 -d > {quoted_path}"
        result = await self._conn.run(cmd)
        if not result.ok:
            raise SSHError(f"write_file({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        if mode is not None:
            chmod = await self._conn.run(f"chmod {mode} {quoted_path}")
            if not chmod.ok:
                raise SSHError(f"chmod {mode} on {remote_path} failed: {chmod.stderr}")

    async def file_exists(self, remote_path: str) -> bool:
        """Check whether ``remote_path`` exists via ``test -e``."""
        result = await self._conn.run(f"test -e {shlex.quote(remote_path)}")
        return result.ok

    async def file_hash(self, remote_path: str, algorithm: str | None = None) -> str:
        """Compute a file hash with no transfer.

        Args:
            remote_path: Absolute path on the remote host.
            algorithm: ``sha256``, ``sha1``, or ``md5``. Defaults to
                ``sha256`` for POSIX hosts.

        Returns:
            Lowercase hex digest.
        """
        algo = (algorithm or self.DEFAULT_HASH).lower()
        if algo not in self._HASH_BINARIES:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        result = await self._conn.run(f"{self._HASH_BINARIES[algo]} {shlex.quote(remote_path)}")
        if not result.ok:
            raise SSHError(f"file_hash({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        return result.stdout.split()[0].lower()

    async def list_directory(self, remote_path: str, *, depth: int = 0) -> list[str]:
        """List items in a directory.

        With ``depth=0`` returns immediate child names. With ``depth>0``
        returns absolute paths up to the recursion limit (uses ``find``
        with ``-mindepth 1 -maxdepth <depth+1>``).
        """
        quoted = shlex.quote(remote_path)
        if depth > 0:
            cmd = f"find {quoted} -mindepth 1 -maxdepth {depth + 1}"
        else:
            cmd = f"ls -1 {quoted}"
        result = await self._conn.run(cmd)
        if not result.ok:
            raise SSHError(f"list_directory({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        return [line for line in result.stdout.splitlines() if line.strip()]
