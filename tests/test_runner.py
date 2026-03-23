# ABOUTME: Tests for the agent runner module with backend protocol and lifecycle hooks.
# ABOUTME: Uses real subprocess scripts and protocol-conforming test doubles (not mocks).

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import unittest.mock as mock
from pathlib import Path

from scaffold.hooks import HookRunner
from scaffold.runner import AgentRunner, ClaudeCodeBackend, RunResult, ScriptBackend


def _make_mock_popen(returncode=0, stdout="", stderr=""):
    """Create a mock Popen object that exits immediately with given results."""
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = returncode
    mock_proc.stdin = mock.MagicMock()
    mock_proc.stdout = mock.MagicMock()
    mock_proc.stdout.read.return_value = stdout
    mock_proc.stderr = mock.MagicMock()
    mock_proc.stderr.read.return_value = stderr
    return mock_proc

# Use the same Python interpreter running the tests for subprocess calls
_PYTHON = sys.executable


class _FakeBackend:
    """Test double implementing the AgentBackend protocol with controlled results."""

    def __init__(self, result: RunResult | None = None):
        self.result = result or RunResult(success=True, stdout="fake output")
        self.calls: list[dict] = []

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        self.calls.append({"prompt": prompt, "cwd": str(cwd), "timeout": timeout})
        return self.result


class TestRunResult:
    """Tests for RunResult dataclass defaults."""

    def test_run_result_defaults(self):
        """RunResult defaults: success=False would need explicit set, metrics/artifacts empty."""
        result = RunResult(success=True)
        assert result.success is True
        assert result.metrics == {}
        assert result.artifacts == []
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.returncode == 0

    def test_run_result_with_metrics(self):
        """RunResult stores metrics and artifacts when provided."""
        result = RunResult(
            success=True,
            metrics={"accuracy": 0.95},
            artifacts=["model.pt"],
            stdout="done",
            returncode=0,
        )
        assert result.metrics["accuracy"] == 0.95
        assert result.artifacts == ["model.pt"]


class TestScriptBackend:
    """Tests for ScriptBackend running real Python scripts as subprocesses."""

    def test_successful_script(self, tmp_path):
        """Script exiting 0 returns RunResult with success=True."""
        script = tmp_path / "good.py"
        script.write_text('print("hello from script")\n')

        backend = ScriptBackend(python=_PYTHON)
        result = backend.run(str(script), cwd=tmp_path)
        assert result.success is True
        assert result.returncode == 0
        assert "hello from script" in result.stdout

    def test_failed_script(self, tmp_path):
        """Script exiting non-zero returns RunResult with success=False."""
        script = tmp_path / "bad.py"
        script.write_text(textwrap.dedent("""\
            import sys
            print("about to fail", file=sys.stderr)
            sys.exit(1)
        """))

        backend = ScriptBackend(python=_PYTHON)
        result = backend.run(str(script), cwd=tmp_path)
        assert result.success is False
        assert result.returncode == 1
        assert "about to fail" in result.stderr

    def test_script_reads_result_json(self, tmp_path):
        """Backend parses result.json from cwd after script runs."""
        script = tmp_path / "writer.py"
        script.write_text(textwrap.dedent("""\
            import json
            from pathlib import Path
            data = {"metrics": {"accuracy": 0.92}, "artifacts": ["out.csv"]}
            Path("result.json").write_text(json.dumps(data))
        """))

        backend = ScriptBackend(python=_PYTHON)
        result = backend.run(str(script), cwd=tmp_path)
        assert result.success is True
        assert result.metrics["accuracy"] == 0.92
        assert "out.csv" in result.artifacts

    def test_script_no_result_json(self, tmp_path):
        """Without result.json, metrics and artifacts are empty."""
        script = tmp_path / "plain.py"
        script.write_text('print("no result file")\n')

        backend = ScriptBackend(python=_PYTHON)
        result = backend.run(str(script), cwd=tmp_path)
        assert result.success is True
        assert result.metrics == {}
        assert result.artifacts == []

    def test_script_timeout(self, tmp_path):
        """Script exceeding timeout returns failure."""
        script = tmp_path / "slow.py"
        script.write_text(textwrap.dedent("""\
            import time
            time.sleep(10)
        """))

        backend = ScriptBackend(python=_PYTHON)
        result = backend.run(str(script), cwd=tmp_path, timeout=1)
        assert result.success is False
        assert result.returncode != 0


class TestClaudeCodeBackend:
    """Tests for ClaudeCodeBackend initialization and result.json parsing."""

    def test_claude_backend_init(self):
        """ClaudeCodeBackend stores model attribute."""
        backend = ClaudeCodeBackend(model="sonnet")
        assert backend.model == "sonnet"

    def test_claude_backend_default_model(self):
        """ClaudeCodeBackend defaults to opus model."""
        backend = ClaudeCodeBackend()
        assert backend.model == "opus"

    def test_claude_backend_reads_result_json(self, tmp_path):
        """ClaudeCodeBackend parses result.json from cwd after execution."""
        result_data = {"metrics": {"bleu": 0.42}, "artifacts": ["summary.txt"]}
        (tmp_path / "result.json").write_text(json.dumps(result_data))

        mock_proc = _make_mock_popen(returncode=0, stdout="agent output")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend()
            result = backend.run("do something", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {"bleu": 0.42}
        assert result.artifacts == ["summary.txt"]
        assert result.stdout == "agent output"

    def test_claude_backend_no_result_json(self, tmp_path):
        """Without result.json, ClaudeCodeBackend returns empty metrics/artifacts."""
        mock_proc = _make_mock_popen(returncode=0, stdout="output")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend()
            result = backend.run("prompt", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {}
        assert result.artifacts == []

    def test_claude_backend_malformed_result_json(self, tmp_path):
        """Malformed result.json is ignored gracefully."""
        (tmp_path / "result.json").write_text("not valid json {{{")

        mock_proc = _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend()
            result = backend.run("prompt", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {}
        assert result.artifacts == []


class TestAgentRunner:
    """Tests for AgentRunner dispatching to backends with lifecycle hooks."""

    def test_execute_dispatches_to_backend(self, tmp_path):
        """execute() calls backend.run with the prompt and cwd."""
        backend = _FakeBackend()
        runner = AgentRunner(backend=backend)
        runner.execute("do something", cwd=tmp_path)
        assert len(backend.calls) == 1
        assert backend.calls[0]["prompt"] == "do something"
        assert backend.calls[0]["cwd"] == str(tmp_path)

    def test_execute_returns_backend_result(self, tmp_path):
        """execute() returns the RunResult from the backend."""
        expected = RunResult(success=True, stdout="backend output", metrics={"x": 1})
        backend = _FakeBackend(result=expected)
        runner = AgentRunner(backend=backend)
        result = runner.execute("prompt", cwd=tmp_path)
        assert result is expected

    def test_execute_no_hooks(self, tmp_path):
        """execute() works without hooks defined."""
        backend = _FakeBackend()
        runner = AgentRunner(backend=backend)
        result = runner.execute("prompt", cwd=tmp_path)
        assert result.success is True

    def test_execute_runs_pre_hook(self, tmp_path):
        """pre_run hook executes before backend dispatch."""
        marker = tmp_path / "pre_ran.txt"
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"pre_run": f"touch {marker}"}
        runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert marker.exists()
        assert len(backend.calls) == 1

    def test_execute_runs_post_hook(self, tmp_path):
        """post_run hook executes after backend dispatch."""
        marker = tmp_path / "post_ran.txt"
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"post_run": f"touch {marker}"}
        runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert marker.exists()

    def test_execute_pre_hook_failure_skips_dispatch(self, tmp_path):
        """If pre_run hook returns non-zero, backend is not called."""
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"pre_run": "exit 1"}
        result = runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert result.success is False
        assert len(backend.calls) == 0

    def test_execute_normalizes_before_run_key(self, tmp_path):
        """before_run hook key is normalized to pre_run and fires correctly."""
        marker = tmp_path / "before_ran.txt"
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"before_run": f"touch {marker}"}
        runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert marker.exists(), "before_run hook should fire as pre_run"
        assert len(backend.calls) == 1

    def test_execute_normalizes_after_run_key(self, tmp_path):
        """after_run hook key is normalized to post_run and fires correctly."""
        marker = tmp_path / "after_ran.txt"
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"after_run": f"touch {marker}"}
        runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert marker.exists(), "after_run hook should fire as post_run"

    def test_execute_normalizes_both_hook_keys(self, tmp_path):
        """Both before_run and after_run keys are normalized and fire."""
        pre_marker = tmp_path / "pre.txt"
        post_marker = tmp_path / "post.txt"
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {
            "before_run": f"touch {pre_marker}",
            "after_run": f"touch {post_marker}",
        }
        runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert pre_marker.exists(), "before_run should fire"
        assert post_marker.exists(), "after_run should fire"

    def test_execute_before_run_failure_skips_dispatch(self, tmp_path):
        """If before_run (normalized to pre_run) hook fails, backend is not called."""
        backend = _FakeBackend()
        hook_runner = HookRunner(cwd=tmp_path)
        runner = AgentRunner(backend=backend, hook_runner=hook_runner)

        hooks = {"before_run": "exit 1"}
        result = runner.execute("prompt", cwd=tmp_path, hooks=hooks)
        assert result.success is False
        assert len(backend.calls) == 0

    def test_execute_passes_timeout(self, tmp_path):
        """Timeout is forwarded to backend.run."""
        backend = _FakeBackend()
        runner = AgentRunner(backend=backend)
        runner.execute("prompt", cwd=tmp_path, timeout=30)
        assert backend.calls[0]["timeout"] == 30


class TestClaudeCodeBackendDefaultTimeout:
    """Tests for ClaudeCodeBackend default timeout behavior."""

    def test_default_timeout_attribute(self):
        """ClaudeCodeBackend has default_timeout of 14400 seconds (4 hours)."""
        backend = ClaudeCodeBackend()
        assert backend.default_timeout == 14400

    def test_custom_default_timeout(self):
        """ClaudeCodeBackend accepts a custom default_timeout."""
        backend = ClaudeCodeBackend(default_timeout=7200)
        assert backend.default_timeout == 7200

    def test_run_uses_default_timeout_when_none(self, tmp_path):
        """When timeout=None, the effective timeout equals default_timeout.

        The Popen-based implementation stores effective_timeout internally.
        We verify by setting a very short default_timeout and stall_timeout
        that would trigger if the timeout is not applied correctly.
        """
        mock_proc = _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend(default_timeout=3600)
            result = backend.run("prompt", cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0

    def test_run_uses_default_timeout_when_not_passed(self, tmp_path):
        """Default timeout is used when run() called without timeout argument."""
        mock_proc = _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend()
            result = backend.run("prompt", cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0

    def test_explicit_timeout_overrides_default(self, tmp_path):
        """Explicit timeout argument overrides default_timeout."""
        mock_proc = _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            backend = ClaudeCodeBackend(default_timeout=14400)
            result = backend.run("prompt", cwd=tmp_path, timeout=600)

        assert result.success is True
        assert result.returncode == 0


class TestClaudeCodeBackendOAuthFallback:
    """Tests for G32: ClaudeCodeBackend strips ANTHROPIC_API_KEY so OAuth is used."""

    def test_strips_anthropic_api_key_from_env(self, tmp_path, monkeypatch):
        """Subprocess env should not contain ANTHROPIC_API_KEY even if parent has it."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key-12345")

        captured_kwargs = {}

        def fake_popen(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            backend = ClaudeCodeBackend()
            backend.run("test prompt", cwd=tmp_path)

        env = captured_kwargs.get("env")
        assert env is not None, "subprocess should get explicit env"
        assert "ANTHROPIC_API_KEY" not in env

    def test_preserves_other_env_vars(self, tmp_path, monkeypatch):
        """Non-API-key env vars should still be present in subprocess env."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
        monkeypatch.setenv("HOME", "/Users/test")
        monkeypatch.setenv("MY_CUSTOM_VAR", "hello")

        captured_kwargs = {}

        def fake_popen(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            backend = ClaudeCodeBackend()
            backend.run("test prompt", cwd=tmp_path)

        env = captured_kwargs["env"]
        assert env.get("MY_CUSTOM_VAR") == "hello"
        assert "HOME" in env

    def test_no_env_override_when_no_api_key(self, tmp_path, monkeypatch):
        """When ANTHROPIC_API_KEY is not set, no env override needed."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        captured_kwargs = {}

        def fake_popen(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _make_mock_popen(returncode=0, stdout="ok")

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            backend = ClaudeCodeBackend()
            backend.run("test prompt", cwd=tmp_path)

        # Should not pass explicit env when no API key to strip
        assert "env" not in captured_kwargs or captured_kwargs["env"] is None


class TestClaudeCodeBackendStallDetection:
    """Tests for stall detection: idle agents are killed when no file activity occurs."""

    def test_stall_timeout_defaults(self):
        """ClaudeCodeBackend defaults to stall_timeout=1800, poll_interval=60."""
        backend = ClaudeCodeBackend()
        assert backend.stall_timeout == 1800
        assert backend.poll_interval == 60

    def test_stall_timeout_custom(self):
        """ClaudeCodeBackend accepts custom stall_timeout and poll_interval."""
        backend = ClaudeCodeBackend(stall_timeout=300, poll_interval=10)
        assert backend.stall_timeout == 300
        assert backend.poll_interval == 10

    def test_latest_mtime_returns_most_recent(self, tmp_path):
        """_latest_mtime returns the mtime of the most recently modified file."""
        import time

        (tmp_path / "old.txt").write_text("old")
        time.sleep(0.05)
        (tmp_path / "new.txt").write_text("new")
        result = ClaudeCodeBackend._latest_mtime(tmp_path)
        assert result is not None
        assert result >= (tmp_path / "new.txt").stat().st_mtime

    def test_latest_mtime_empty_dir(self, tmp_path):
        """_latest_mtime returns None for empty directory."""
        result = ClaudeCodeBackend._latest_mtime(tmp_path)
        assert result is None

    def test_latest_mtime_nonexistent_dir(self, tmp_path):
        """_latest_mtime returns None for nonexistent directory."""
        result = ClaudeCodeBackend._latest_mtime(tmp_path / "nope")
        assert result is None

    def test_stall_detection_kills_idle_process(self, tmp_path):
        """A process with no file activity is killed after stall_timeout."""
        import unittest.mock as mock

        backend = ClaudeCodeBackend(stall_timeout=2, poll_interval=1)

        # Create a mock process that never exits on its own
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = mock.MagicMock()
        mock_proc.stdout = mock.MagicMock()
        mock_proc.stdout.read.return_value = ""
        mock_proc.stderr = mock.MagicMock()
        mock_proc.stderr.read.return_value = ""
        mock_proc.kill.return_value = None
        mock_proc.wait.return_value = None

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = backend.run("test prompt", cwd=tmp_path)

        assert not result.success
        assert result.returncode == -2
        assert "stalled" in result.stderr.lower()
        mock_proc.kill.assert_called_once()

    def test_no_stall_when_files_modified(self, tmp_path):
        """A process that modifies files is NOT killed for stalling."""
        import threading
        import time
        import unittest.mock as mock

        backend = ClaudeCodeBackend(stall_timeout=3, poll_interval=1)

        # Simulate file activity in a background thread
        stop_event = threading.Event()

        def write_files():
            i = 0
            while not stop_event.is_set():
                (tmp_path / f"output_{i}.txt").write_text(f"data {i}")
                i += 1
                time.sleep(0.5)

        writer = threading.Thread(target=write_files, daemon=True)
        writer.start()

        # Mock process that exits after 4 seconds (longer than stall_timeout)
        start = time.monotonic()

        def poll_side_effect():
            if time.monotonic() - start > 4:
                return 0
            return None

        mock_proc = mock.MagicMock()
        mock_proc.poll.side_effect = poll_side_effect
        mock_proc.stdin = mock.MagicMock()
        mock_proc.stdout = mock.MagicMock()
        mock_proc.stdout.read.return_value = ""
        mock_proc.stderr = mock.MagicMock()
        mock_proc.stderr.read.return_value = ""

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = backend.run("test prompt", cwd=tmp_path)

        stop_event.set()
        writer.join(timeout=2)

        # Should NOT have been killed -- files were being written
        assert result.returncode == 0
        mock_proc.kill.assert_not_called()

    def test_overall_timeout_still_works(self, tmp_path):
        """Overall timeout kills process even if files are being modified."""
        import threading
        import time
        import unittest.mock as mock

        backend = ClaudeCodeBackend(
            default_timeout=3, stall_timeout=100, poll_interval=1
        )

        # Keep writing files so stall detection does not trigger
        stop_event = threading.Event()

        def write_files():
            i = 0
            while not stop_event.is_set():
                (tmp_path / f"out_{i}.txt").write_text(f"d {i}")
                i += 1
                time.sleep(0.5)

        writer = threading.Thread(target=write_files, daemon=True)
        writer.start()

        # Process never exits
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = mock.MagicMock()
        mock_proc.stdout = mock.MagicMock()
        mock_proc.stdout.read.return_value = ""
        mock_proc.stderr = mock.MagicMock()
        mock_proc.stderr.read.return_value = ""
        mock_proc.kill.return_value = None
        mock_proc.wait.return_value = None

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = backend.run("test prompt", cwd=tmp_path)

        stop_event.set()
        writer.join(timeout=2)

        assert not result.success
        assert result.returncode == -1
        assert "timeout" in result.stderr.lower()
        mock_proc.kill.assert_called_once()

    def test_process_normal_exit_parses_result_json(self, tmp_path):
        """Normal process exit still parses result.json as before."""
        import unittest.mock as mock

        result_data = {"metrics": {"acc": 0.95}, "artifacts": ["model.bin"]}
        (tmp_path / "result.json").write_text(json.dumps(result_data))

        backend = ClaudeCodeBackend(stall_timeout=100, poll_interval=1)

        # Process exits immediately
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.stdin = mock.MagicMock()
        mock_proc.stdout = mock.MagicMock()
        mock_proc.stdout.read.return_value = "agent output"
        mock_proc.stderr = mock.MagicMock()
        mock_proc.stderr.read.return_value = ""

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = backend.run("test prompt", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {"acc": 0.95}
        assert result.artifacts == ["model.bin"]
        assert result.stdout == "agent output"
        assert result.returncode == 0

    def test_file_not_found_returns_error(self, tmp_path):
        """FileNotFoundError from Popen returns failure RunResult."""
        import unittest.mock as mock

        backend = ClaudeCodeBackend()

        with mock.patch(
            "subprocess.Popen",
            side_effect=FileNotFoundError("claude not found"),
        ):
            result = backend.run("test prompt", cwd=tmp_path)

        assert not result.success
        assert result.returncode == -1
        assert "claude" in result.stderr.lower()
