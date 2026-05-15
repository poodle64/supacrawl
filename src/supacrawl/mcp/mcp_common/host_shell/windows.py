"""Windows host-shell implementation.

File operations expressed as PowerShell scripts piped over stdin to
``powershell -Command -``. Stdin piping sidesteps the well-known
quote-escaping problems of PowerShell over SSH; binary or
quote-heavy payloads are base64-encoded and decoded server-side.

Constructed with a shared :class:`mcp_common.executors.SSHConnection`.
The connection itself is OS-agnostic; this class is the Windows
vocabulary on top of it.
"""

from __future__ import annotations

import base64
import json

from ..executors.ssh import SSHConnection, SSHError, SSHResult


class WindowsHostShell:
    """File operations on a Windows remote host running OpenSSH server.

    Implements :class:`HostShell` plus Windows-only conveniences
    (``run_powershell`` for arbitrary scripts, ``disk_usage`` for drive
    free space).
    """

    DEFAULT_HASH = "SHA1"

    def __init__(self, connection: SSHConnection) -> None:
        self._conn = connection

    async def run_powershell(self, script: str, timeout: float = SSHConnection.DEFAULT_TIMEOUT) -> SSHResult:
        """Run a PowerShell script via stdin.

        Public because some callers need to run domain-specific scripts
        that don't fit the file-shaped vocabulary (e.g. service control,
        registry queries).
        """
        return await self._conn.run("powershell -Command -", timeout=timeout, stdin=script)

    async def read_file(self, remote_path: str) -> str:
        """Read a file via ``Get-Content -Encoding UTF8 -Raw``."""
        result = await self.run_powershell(f"Get-Content -Path '{remote_path}' -Encoding UTF8 -Raw")
        if not result.ok:
            raise SSHError(f"read_file({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        return result.stdout

    async def write_file(self, remote_path: str, content: str, *, mode: str | None = None) -> None:
        """Write a file via base64-decoded ``WriteAllText``.

        ``mode`` is accepted for protocol compatibility and ignored on
        Windows; ACLs are not managed here.
        """
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        script = (
            f"$bytes = [Convert]::FromBase64String('{encoded}')\n"
            f"$text = [System.Text.Encoding]::UTF8.GetString($bytes)\n"
            f"[System.IO.File]::WriteAllText('{remote_path}', $text)"
        )
        result = await self.run_powershell(script)
        if not result.ok:
            raise SSHError(f"write_file({remote_path}) failed (exit {result.exit_status}): {result.stderr}")

    async def file_exists(self, remote_path: str) -> bool:
        """Check whether ``remote_path`` exists via ``Test-Path``."""
        result = await self.run_powershell(f"Test-Path '{remote_path}'")
        return result.stdout.strip().lower() == "true"

    async def file_hash(self, remote_path: str, algorithm: str | None = None) -> str:
        """Compute a file hash via ``Get-FileHash``.

        Args:
            remote_path: Path on the Windows host.
            algorithm: PowerShell hash name (``SHA1``, ``SHA256``,
                ``MD5``, etc.). Defaults to ``SHA1`` for parity with
                gamekeeper's existing No-Intro validation flow.

        Returns:
            Hex digest (case as PowerShell returns it; typically upper).
        """
        algo = algorithm or self.DEFAULT_HASH
        result = await self.run_powershell(f"(Get-FileHash -Path '{remote_path}' -Algorithm {algo}).Hash")
        if not result.ok:
            raise SSHError(f"file_hash({remote_path}) failed (exit {result.exit_status}): {result.stderr}")
        return result.stdout.strip()

    async def list_directory(self, remote_path: str, *, depth: int = 0) -> list[str]:
        """List items in a directory.

        With ``depth=0`` returns immediate child names; otherwise
        returns full paths up to the given recursion depth.
        """
        if depth > 0:
            script = (
                f"Get-ChildItem -Path '{remote_path}' -Recurse -Depth {depth} | Select-Object -ExpandProperty FullName"
            )
        else:
            script = f"Get-ChildItem -Path '{remote_path}' | Select-Object -ExpandProperty Name"
        result = await self.run_powershell(script)
        if not result.stdout:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    async def disk_usage(self) -> dict[str, dict[str, int]]:
        """Return per-drive disk usage on the Windows host.

        Returns:
            Mapping of drive letter to ``{used, free, total}`` in bytes.
        """
        script = "Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free | ConvertTo-Json"
        result = await self.run_powershell(script)
        if not result.stdout:
            return {}
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        drives: dict[str, dict[str, int]] = {}
        for drive in data:
            name = drive.get("Name", "")
            used = int(drive.get("Used", 0) or 0)
            free = int(drive.get("Free", 0) or 0)
            drives[name] = {"used": used, "free": free, "total": used + free}
        return drives
