# ABOUTME: Agent runner with backend protocol for dispatching work to different execution backends.
# ABOUTME: Supports script subprocess execution, Claude CLI dispatch, and lifecycle hooks.

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from scaffold.hooks import HookRunner


@dataclass
class RunResult:
    """Result from an agent/script run."""

    success: bool
    metrics: dict = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class AgentBackend(Protocol):
    """Protocol for agent execution backends."""

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        """Execute a prompt/script and return results."""
        ...


class ScriptBackend:
    """Runs Python scripts as subprocesses."""

    def __init__(self, python: str = ".venv/bin/python"):
        self.python = python

    def run(self, script_path: str, cwd: Path, timeout: int | None = None) -> RunResult:
        """Run a Python script. Parses result.json from cwd after execution."""
        try:
            proc = subprocess.run(
                [self.python, script_path],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                success=False,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace"),
                stderr=exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace"),
                returncode=-1,
            )

        metrics: dict = {}
        artifacts: list[str] = []

        result_json_path = cwd / "result.json"
        if result_json_path.exists():
            try:
                data = json.loads(result_json_path.read_text())
                metrics = data.get("metrics", {})
                artifacts = data.get("artifacts", [])
            except (json.JSONDecodeError, KeyError):
                pass

        return RunResult(
            success=proc.returncode == 0,
            metrics=metrics,
            artifacts=artifacts,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )


class ClaudeCodeBackend:
    """Launches claude --print with a rendered prompt and stall detection."""

    def __init__(
        self,
        model: str = "opus",
        default_timeout: int = 14400,
        stall_timeout: int = 1800,
        poll_interval: int = 60,
    ):
        self.model = model
        self.default_timeout = default_timeout
        self.stall_timeout = stall_timeout
        self.poll_interval = poll_interval

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        """Run claude --print with stall detection.

        Uses Popen with polling to detect stalled agents. If no file in cwd
        is modified for stall_timeout seconds, the agent is killed and a
        failure is returned.
        """
        # Strip ANTHROPIC_API_KEY so claude CLI uses OAuth instead of API credits
        env = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        effective_timeout = timeout if timeout is not None else self.default_timeout

        try:
            proc = subprocess.Popen(
                [
                    "claude", "--print",
                    "--model", self.model,
                    "--dangerously-skip-permissions",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            return RunResult(
                success=False,
                stderr=f"claude CLI not found: {exc}",
                returncode=-1,
            )

        # Write prompt to stdin and close it
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass

        start_time = time.monotonic()
        last_activity = start_time

        while True:
            # Check if process has exited
            retcode = proc.poll()
            if retcode is not None:
                stdout = proc.stdout.read() if proc.stdout else ""
                stderr = proc.stderr.read() if proc.stderr else ""
                break

            # Check overall timeout
            elapsed = time.monotonic() - start_time
            if elapsed > effective_timeout:
                proc.kill()
                proc.wait()
                stdout = proc.stdout.read() if proc.stdout else ""
                stderr = proc.stderr.read() if proc.stderr else ""
                return RunResult(
                    success=False,
                    stdout=stdout,
                    stderr="Timeout expired",
                    returncode=-1,
                )

            # Check file activity (stall detection)
            try:
                latest_mtime = self._latest_mtime(cwd)
                if latest_mtime is not None and latest_mtime > last_activity:
                    last_activity = time.monotonic()
            except OSError:
                pass

            stall_duration = time.monotonic() - last_activity
            if stall_duration > self.stall_timeout:
                proc.kill()
                proc.wait()
                stdout = proc.stdout.read() if proc.stdout else ""
                stderr = proc.stderr.read() if proc.stderr else ""
                return RunResult(
                    success=False,
                    stdout=stdout,
                    stderr=f"Agent stalled: no file activity for {self.stall_timeout} seconds",
                    returncode=-2,
                )

            time.sleep(self.poll_interval)

        # Process exited normally -- parse result.json
        metrics: dict = {}
        artifacts: list[str] = []

        result_json_path = cwd / "result.json"
        if result_json_path.exists():
            try:
                data = json.loads(result_json_path.read_text())
                metrics = data.get("metrics", {})
                artifacts = data.get("artifacts", [])
            except (json.JSONDecodeError, KeyError):
                pass

        return RunResult(
            success=retcode == 0,
            metrics=metrics,
            artifacts=artifacts,
            stdout=stdout,
            stderr=stderr,
            returncode=retcode,
        )

    @staticmethod
    def _latest_mtime(directory: Path) -> float | None:
        """Return the most recent mtime of any file in directory, or None."""
        latest = None
        try:
            for f in directory.rglob("*"):
                if f.is_file():
                    try:
                        mt = f.stat().st_mtime
                        if latest is None or mt > latest:
                            latest = mt
                    except OSError:
                        continue
        except OSError:
            pass
        return latest


class AgentRunner:
    """Orchestrates a single run: hooks -> dispatch -> hooks -> result."""

    def __init__(self, backend: AgentBackend, hook_runner: HookRunner | None = None):
        self.backend = backend
        self.hook_runner = hook_runner

    def execute(
        self,
        prompt_or_script: str,
        cwd: Path,
        hooks: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> RunResult:
        """Execute a run with lifecycle hooks.

        1. Run pre_run hook if defined
        2. Dispatch to backend
        3. Run post_run hook if defined
        4. Return RunResult

        If pre_run hook fails, skip dispatch and return failure RunResult.
        """
        hooks = hooks or {}

        # Normalize hook key names (accept both before_run/after_run and pre_run/post_run)
        normalized: dict[str, str] = {}
        for k, v in hooks.items():
            if k == "before_run":
                normalized["pre_run"] = v
            elif k == "after_run":
                normalized["post_run"] = v
            else:
                normalized[k] = v
        hooks = normalized

        # Run pre_run hook
        if "pre_run" in hooks and self.hook_runner:
            result = self.hook_runner.run_hook("pre_run", hooks["pre_run"])
            if result.returncode != 0:
                return RunResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                )

        # Dispatch to backend
        run_result = self.backend.run(prompt_or_script, cwd, timeout=timeout)

        # Run post_run hook
        if "post_run" in hooks and self.hook_runner:
            self.hook_runner.run_hook("post_run", hooks["post_run"])

        return run_result
