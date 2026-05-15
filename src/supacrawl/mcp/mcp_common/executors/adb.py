"""ADB executor for Android device management.

Wraps ``adb`` subprocess calls so MCP servers never have to shell out directly.
Used by android (Fenrir, Firesticks, tablets) and any future household
Android MCP servers.

Transport selection:

- USB is the primary transport; android always tries USB first via
  ``adb -s <serial>`` when a device serial is configured, otherwise via the
  default ``adb`` target selection.
- Wireless ADB is opportunistic. When ``adb_host`` is set (e.g.
  ``10.0.1.5:5555``) the executor attempts ``adb connect`` once per session
  and falls back to USB on failure. GrapheneOS intentionally disables the
  wireless-debugging toggle on every reboot (hardening), so wireless cannot
  be relied upon across reboots.

All commands run with an explicit timeout. Output is captured. Non-zero exit
statuses are returned in the result rather than raised, so callers can decide
whether a failing ``pm list`` matters or not.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ADBResult:
    """Result of an ADB command.

    Attributes:
        stdout: Captured standard output, stripped.
        stderr: Captured standard error, stripped.
        exit_status: Process exit status; 0 is success.
        command: The full command that was run (for diagnostics).
    """

    stdout: str
    stderr: str
    exit_status: int
    command: str

    @property
    def ok(self) -> bool:
        """True when exit_status is 0."""
        return self.exit_status == 0


class ADBConnectionError(RuntimeError):
    """Raised when ADB cannot reach the target device.

    Servers should catch this and translate it into their own exception
    hierarchy (see :mod:`mcp_common.exceptions`).
    """


class ADBExecutor:
    """Execute ADB commands against a single Android device.

    A single executor instance represents one logical device target. Multi-
    device support is out of scope at this layer; if you need butterfly and
    spider too, instantiate one executor per device.

    Args:
        adb_binary: Absolute path to ``adb``, or just ``adb`` to rely on PATH.
        serial: Optional device serial for ``adb -s <serial>``. Required when
            multiple devices are attached.
        adb_host: Optional wireless ADB endpoint (``host:port``). When set the
            executor attempts ``adb connect`` on first use.
        default_timeout: Default command timeout in seconds.
    """

    def __init__(
        self,
        adb_binary: str = "adb",
        serial: str | None = None,
        adb_host: str | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        self._adb = adb_binary
        self._serial = serial
        self._adb_host = adb_host
        self._default_timeout = default_timeout
        self._wireless_attempted = False
        self._wireless_connected = False

    async def connect(self) -> None:
        """Attempt to connect to the device.

        If ``adb_host`` is set, runs ``adb connect <host>`` once. Any failure
        is logged at WARNING level but does not raise; the caller can still
        use USB transport if it is available.

        Always runs ``adb get-state`` at the end so failures surface as an
        :class:`ADBConnectionError` before the first tool call.
        """
        if self._adb_host and not self._wireless_attempted:
            self._wireless_attempted = True
            result = await self._run_raw([self._adb, "connect", self._adb_host], timeout=10.0)
            if result.ok and "connected" in result.stdout.lower():
                self._wireless_connected = True
                logger.info("Wireless ADB connected to %s", self._adb_host)
            else:
                logger.warning(
                    "Wireless ADB connect to %s failed: %s",
                    self._adb_host,
                    result.stdout or result.stderr,
                )

        state = await self._run_raw([*self._base_cmd(), "get-state"], timeout=5.0)
        if not state.ok:
            raise ADBConnectionError(
                "ADB cannot reach the device. "
                "Plug the phone in via USB, or enable Wireless debugging "
                "in Developer Options and rerun. "
                f"adb get-state said: {state.stdout or state.stderr!r}"
            )
        logger.info("ADB device state: %s", state.stdout.strip())

    async def close(self) -> None:
        """Close the executor.

        Wireless connections are left as-is; ``adb disconnect`` would affect
        concurrent users of the same device.
        """

    async def shell(self, command: str, timeout: float | None = None) -> ADBResult:
        """Run ``adb shell <command>`` on the device.

        Args:
            command: Shell command to execute on the device.
            timeout: Optional per-call timeout (seconds).

        Returns:
            An :class:`ADBResult` with captured output and exit status.
        """
        return await self._run_raw(
            [*self._base_cmd(), "shell", command],
            timeout=timeout or self._default_timeout,
        )

    async def raw(self, args: list[str], timeout: float | None = None) -> ADBResult:
        """Run a raw ``adb`` invocation (no implicit ``shell``).

        Use for ``adb install``, ``adb push``, ``adb pull``, ``adb get-state``.

        Args:
            args: Tokens to append after the base command.
            timeout: Optional per-call timeout (seconds).

        Returns:
            An :class:`ADBResult`.
        """
        return await self._run_raw([*self._base_cmd(), *args], timeout=timeout or self._default_timeout)

    async def install(
        self,
        apk_path: Path,
        replace: bool = True,
        downgrade: bool = False,
        grant_runtime_perms: bool = False,
        target_user: int | None = None,
        extra_flags: list[str] | None = None,
    ) -> ADBResult:
        """Install an APK from the host filesystem.

        Args:
            apk_path: Absolute path to the ``.apk`` on the host.
            replace: Pass ``-r`` to replace an existing install (default).
            downgrade: Pass ``-d`` to allow installing an older version
                over a newer one. Off by default; downgrades can break
                data migrations.
            grant_runtime_perms: Pass ``-g`` to grant every runtime
                permission declared in the manifest at install time.
            target_user: Pass ``--user <id>``. ``None`` lets adb pick.
            extra_flags: Additional ``pm install`` flags as a list of
                tokens (e.g. ``["--bypass-low-target-sdk-block"]``).
                Power-user escape hatch; the bool flags above cover the
                common cases.
        """
        args = ["install"]
        if replace:
            args.append("-r")
        if downgrade:
            args.append("-d")
        if grant_runtime_perms:
            args.append("-g")
        if target_user is not None:
            args.extend(["--user", str(target_user)])
        if extra_flags:
            args.extend(extra_flags)
        args.append(str(apk_path))
        return await self.raw(args, timeout=180.0)

    async def uninstall(self, package: str, keep_data: bool = False) -> ADBResult:
        """Uninstall a package.

        Args:
            package: Android package name, e.g. ``com.example.app``.
            keep_data: Pass ``-k`` to preserve application data and cache.
        """
        args = ["uninstall"]
        if keep_data:
            args.append("-k")
        args.append(package)
        return await self.raw(args, timeout=60.0)

    async def push(self, local: Path, remote: str) -> ADBResult:
        """Push a file from the host to the device."""
        return await self.raw(["push", str(local), remote], timeout=180.0)

    async def pull(self, remote: str, local: Path) -> ADBResult:
        """Pull a file from the device to the host."""
        return await self.raw(["pull", remote, str(local)], timeout=180.0)

    async def package_path(self, package: str) -> str | None:
        """Resolve the on-device path to a package's APK.

        Returns ``None`` if the package is not installed. Handles the
        ``package:`` prefix that ``pm path`` emits.
        """
        result = await self.shell(f"pm path {package}")
        if not result.ok or not result.stdout:
            return None
        first_line = result.stdout.splitlines()[0].strip()
        return first_line.removeprefix("package:") or None

    def _base_cmd(self) -> list[str]:
        """Base command with ``-s <target>`` when one is configured.

        Wireless ADB devices appear in ``adb devices`` output as
        ``host:port`` and are valid ``-s`` arguments; pass them through
        so commands target the right device when multiple are on the bus.
        """
        target = self._serial or self._adb_host
        if target:
            return [self._adb, "-s", target]
        return [self._adb]

    async def _run_raw(self, argv: list[str], timeout: float) -> ADBResult:
        """Spawn a subprocess and return an :class:`ADBResult`."""
        command_str = " ".join(argv)
        logger.debug("adb exec: %s (timeout=%.1fs)", command_str, timeout)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ADBConnectionError(
                f"adb binary not found at {argv[0]!r}. Install android-tools via nixpkgs or set ADB_BINARY."
            ) from exc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ADBConnectionError(f"adb command timed out after {timeout:.1f}s: {command_str}") from exc

        return ADBResult(
            stdout=(stdout_b or b"").decode("utf-8", errors="replace").strip(),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace").strip(),
            exit_status=proc.returncode or 0,
            command=command_str,
        )
