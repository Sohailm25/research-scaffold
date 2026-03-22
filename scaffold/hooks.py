# ABOUTME: Executes lifecycle hooks (shell commands) at defined points in the agent runner lifecycle.
# ABOUTME: Provides HookRunner with subprocess execution, timeout handling, and fail-fast semantics.

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HookResult:
    """Result of executing a single hook command."""

    hook_name: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


class HookRunner:
    """Executes shell hook commands as subprocesses with timeout and ordering."""

    def __init__(self, cwd: Path, timeout: int = 60):
        """Initialize with working directory and timeout for hook commands."""
        self.cwd = cwd
        self.timeout = timeout

    def run_hook(self, name: str, command: str) -> HookResult:
        """Execute a hook command as a subprocess.

        Args:
            name: Hook name (e.g., "pre_run", "post_run")
            command: Shell command to execute

        Returns HookResult with exit code, stdout, stderr, duration.
        Does NOT raise on non-zero exit - returns the result for caller to decide.
        """
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration = time.monotonic() - start
            return HookResult(
                hook_name=name,
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            return HookResult(
                hook_name=name,
                command=command,
                returncode=-1,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace"),
                stderr=exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace"),
                duration_seconds=duration,
            )

    def run_hooks(self, hooks: dict[str, str]) -> list[HookResult]:
        """Run multiple hooks in order. Returns list of results.

        Stops on first non-zero exit code (fail-fast).
        Skips hooks with empty/None commands.
        """
        results: list[HookResult] = []
        for name, command in hooks.items():
            if not command:
                continue
            result = self.run_hook(name, command)
            results.append(result)
            if result.returncode != 0:
                break
        return results
