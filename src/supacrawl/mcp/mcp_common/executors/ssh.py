"""Shared SSH connection for MCP servers.

A thin wrapper around :mod:`asyncssh` that owns connection lifecycle:
caching with keepalive, exponential-backoff reconnect, command execution,
and SFTP transfer. It does **not** know anything about file shapes,
shells, or the remote host's OS; that vocabulary lives in
:mod:`mcp_common.host_shell`.

A consumer typically composes one ``SSHConnection`` with one
``HostShell`` of the right flavour. For servers that only run remote
commands (``unbound-control``, ``docker exec``, ``systemctl``) and
never touch files, the bare ``SSHConnection`` is enough.

Failures bubble up as :class:`SSHError`. Servers can catch this directly
or apply :func:`mcp_common.exceptions.translate_exceptions` to map it
into their own hierarchy at the boundary.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import asyncssh

logger = logging.getLogger(__name__)


def _to_str(value: bytes | str | None) -> str:
    """Coerce asyncssh's ``bytes | str | None`` output to a plain string."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclass(frozen=True)
class SSHResult:
    """Result of a remote command.

    Attributes:
        stdout: Captured standard output, stripped.
        stderr: Captured standard error, stripped.
        exit_status: Process exit status; 0 is success.
    """

    stdout: str
    stderr: str
    exit_status: int

    @property
    def ok(self) -> bool:
        """True when the command exited successfully."""
        return self.exit_status == 0


class SSHError(RuntimeError):
    """Connection or command-execution failure on an :class:`SSHConnection`.

    Servers either catch this directly or translate it into their own
    exception hierarchy at the tool boundary.
    """


class SSHConnection:
    """A cached asyncssh connection with auto-reconnect and SFTP transfer.

    Owns one logical SSH session to a remote host. The connection is
    established lazily on first use, kept warm with a 60 second
    keepalive, and reconnected with exponential backoff if the cached
    handle goes stale.
    """

    MAX_RETRIES = 3
    BACKOFF_DELAYS = (1, 2, 4)
    DEFAULT_TIMEOUT = 30.0
    SFTP_TIMEOUT = 600.0

    def __init__(self, host: str, user: str, key_path: str = "") -> None:
        """Initialise the connection.

        Args:
            host: Remote hostname or SSH alias.
            user: Remote username.
            key_path: Path to a private key file. If empty, asyncssh's
                default key discovery is used.
        """
        self._host = host
        self._user = user
        self._key_path = key_path
        self._connection: asyncssh.SSHClientConnection | None = None

    @property
    def endpoint(self) -> str:
        """Human-readable ``ssh://user@host`` endpoint for diagnostics."""
        return f"ssh://{self._user}@{self._host}"

    async def _open(self) -> asyncssh.SSHClientConnection:
        """Get or create the cached connection, retrying on failure."""
        if self._connection is not None:
            try:
                await self._connection.run("echo ok", check=True, timeout=5)
                return self._connection
            except Exception:
                logger.warning("Stale SSH connection detected; reconnecting")
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None

        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                connect_kwargs: dict[str, Any] = {
                    "host": self._host,
                    "username": self._user,
                    "known_hosts": None,
                    "keepalive_interval": 60,
                }
                if self._key_path:
                    connect_kwargs["client_keys"] = [self._key_path]
                self._connection = await asyncssh.connect(**connect_kwargs)
                logger.info("SSH connection established to %s@%s", self._user, self._host)
                return self._connection
            except (asyncssh.Error, OSError) as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.BACKOFF_DELAYS[attempt]
                    logger.warning(
                        "SSH connection attempt %d/%d failed: %s (retrying in %ds)",
                        attempt + 1,
                        self.MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise SSHError(f"SSH connection failed after {self.MAX_RETRIES} attempts: {last_error}")

    async def run(
        self,
        cmd: str,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        stdin: str | None = None,
    ) -> SSHResult:
        """Execute a command on the remote host.

        Args:
            cmd: Command string to execute.
            timeout: Timeout in seconds.
            stdin: Optional stdin payload. Useful for piping a script
                to a remote interpreter (e.g. ``powershell -Command -``).

        Returns:
            SSHResult with stdout, stderr, and exit status. A non-zero
            exit status is returned, not raised; callers decide whether
            it matters.

        Raises:
            SSHError: On connection failure or asyncssh-level error.
        """
        try:
            conn = await self._open()
            kwargs: dict[str, Any] = {"timeout": timeout}
            if stdin is not None:
                kwargs["input"] = stdin
            result = await conn.run(cmd, **kwargs)
            return SSHResult(
                stdout=_to_str(result.stdout).strip(),
                stderr=_to_str(result.stderr).strip(),
                exit_status=result.exit_status or 0,
            )
        except SSHError:
            raise
        except (asyncssh.Error, OSError) as exc:
            raise SSHError(f"Command execution failed: {exc}") from exc

    async def upload(self, local_path: str, remote_path: str, timeout: float = SFTP_TIMEOUT) -> None:
        """Upload a local file to the remote host via SFTP.

        SFTP rather than SCP because it handles filenames with spaces,
        parentheses, and special characters reliably across platforms.

        Args:
            local_path: Local file path.
            remote_path: Destination path on the remote host.
            timeout: Transfer timeout in seconds.

        Raises:
            SSHError: On SFTP failure.
        """
        try:
            conn = await self._open()

            async def _do_sftp() -> None:
                async with conn.start_sftp_client() as sftp:
                    await sftp.put(local_path, remote_path)

            await asyncio.wait_for(_do_sftp(), timeout=timeout)
        except SSHError:
            raise
        except (asyncssh.Error, OSError, asyncio.TimeoutError) as exc:
            raise SSHError(f"SFTP transfer failed: {exc}") from exc

    async def close(self) -> None:
        """Close the cached SSH connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("SSH connection closed")
