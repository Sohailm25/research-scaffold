# ABOUTME: Tests for scaffold/hooks.py - HookRunner lifecycle hook execution.
# ABOUTME: Covers hook execution, stdout/stderr capture, timeouts, fail-fast, and skip behavior.

import pytest

from scaffold.hooks import HookResult, HookRunner


class TestHookResult:
    def test_hook_result_fields(self):
        r = HookResult(
            hook_name="pre_run",
            command="echo hello",
            returncode=0,
            stdout="hello\n",
            stderr="",
            duration_seconds=0.01,
        )
        assert r.hook_name == "pre_run"
        assert r.command == "echo hello"
        assert r.returncode == 0
        assert r.stdout == "hello\n"
        assert r.stderr == ""
        assert r.duration_seconds == 0.01


class TestRunHook:
    def test_successful_hook(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "echo hello")
        assert result.returncode == 0
        assert result.hook_name == "test"

    def test_failed_hook(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "false")
        assert result.returncode != 0

    def test_hook_captures_stdout(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "echo captured_output")
        assert "captured_output" in result.stdout

    def test_hook_captures_stderr(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "echo error_msg >&2")
        assert "error_msg" in result.stderr

    def test_hook_timeout(self, tmp_path):
        runner = HookRunner(cwd=tmp_path, timeout=1)
        result = runner.run_hook("test", "sleep 10")
        assert result.returncode != 0
        assert result.duration_seconds >= 0.5  # should have waited at least a bit

    def test_hook_cwd(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "pwd")
        assert str(tmp_path) in result.stdout

    def test_hook_duration_recorded(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        result = runner.run_hook("test", "echo fast")
        assert result.duration_seconds >= 0.0


class TestRunHooks:
    def test_run_multiple_hooks(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        hooks = {"first": "echo one", "second": "echo two"}
        results = runner.run_hooks(hooks)
        assert len(results) == 2
        assert results[0].hook_name == "first"
        assert results[1].hook_name == "second"
        assert all(r.returncode == 0 for r in results)

    def test_fail_fast(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        hooks = {"first": "echo ok", "second": "false", "third": "echo should_not_run"}
        results = runner.run_hooks(hooks)
        assert len(results) == 2  # stopped after second (failed)
        assert results[0].returncode == 0
        assert results[1].returncode != 0

    def test_skip_empty_hooks(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        hooks = {"first": "echo ok", "second": None, "third": "", "fourth": "echo end"}
        results = runner.run_hooks(hooks)
        assert len(results) == 2  # only non-empty hooks
        assert results[0].hook_name == "first"
        assert results[1].hook_name == "fourth"

    def test_empty_hooks_dict(self, tmp_path):
        runner = HookRunner(cwd=tmp_path)
        results = runner.run_hooks({})
        assert results == []
