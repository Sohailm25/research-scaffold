# ABOUTME: Tests for the agent runner module with backend protocol and lifecycle hooks.
# ABOUTME: Uses real subprocess scripts and protocol-conforming test doubles (not mocks).

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from scaffold.hooks import HookRunner
from scaffold.runner import AgentRunner, ClaudeCodeBackend, RunResult, ScriptBackend

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

    def test_claude_backend_reads_result_json(self, tmp_path, monkeypatch):
        """ClaudeCodeBackend parses result.json from cwd after execution."""
        result_data = {"metrics": {"bleu": 0.42}, "artifacts": ["summary.txt"]}
        (tmp_path / "result.json").write_text(json.dumps(result_data))

        fake_proc = subprocess.CompletedProcess(
            args=["claude", "--print", "--model", "opus"],
            returncode=0,
            stdout="agent output",
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)

        backend = ClaudeCodeBackend()
        result = backend.run("do something", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {"bleu": 0.42}
        assert result.artifacts == ["summary.txt"]
        assert result.stdout == "agent output"

    def test_claude_backend_no_result_json(self, tmp_path, monkeypatch):
        """Without result.json, ClaudeCodeBackend returns empty metrics/artifacts."""
        fake_proc = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="output", stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)

        backend = ClaudeCodeBackend()
        result = backend.run("prompt", cwd=tmp_path)

        assert result.success is True
        assert result.metrics == {}
        assert result.artifacts == []

    def test_claude_backend_malformed_result_json(self, tmp_path, monkeypatch):
        """Malformed result.json is ignored gracefully."""
        (tmp_path / "result.json").write_text("not valid json {{{")

        fake_proc = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="ok", stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)

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

    def test_run_uses_default_timeout_when_none(self, tmp_path, monkeypatch):
        """When timeout=None, subprocess.run receives default_timeout."""
        captured_kwargs = {}

        def fake_run(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="ok", stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = ClaudeCodeBackend(default_timeout=3600)
        backend.run("prompt", cwd=tmp_path)

        assert captured_kwargs["timeout"] == 3600

    def test_run_uses_default_timeout_when_not_passed(self, tmp_path, monkeypatch):
        """Default timeout is used when run() called without timeout argument."""
        captured_kwargs = {}

        def fake_run(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="ok", stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = ClaudeCodeBackend()
        backend.run("prompt", cwd=tmp_path)

        assert captured_kwargs["timeout"] == 14400

    def test_explicit_timeout_overrides_default(self, tmp_path, monkeypatch):
        """Explicit timeout argument overrides default_timeout."""
        captured_kwargs = {}

        def fake_run(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="ok", stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend = ClaudeCodeBackend(default_timeout=14400)
        backend.run("prompt", cwd=tmp_path, timeout=600)

        assert captured_kwargs["timeout"] == 600
