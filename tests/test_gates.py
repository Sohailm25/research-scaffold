# ABOUTME: Tests for scaffold/gates.py - phase gate evaluation engine.
# ABOUTME: Covers gate evaluation per comparator, SKIP/ERROR states, and phase-level aggregation.

import pytest

from scaffold.config import GateConfig, PhaseConfig
from scaffold.gates import GateResult, PhaseGateReport, evaluate_gate, evaluate_phase_gates


# --- evaluate_gate: PASS cases ---


class TestEvaluateGatePass:
    def test_gte_pass_equal(self):
        gate = GateConfig(metric="score", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.5})
        assert result.status == "PASS"
        assert result.observed_value == 0.5

    def test_gte_pass_above(self):
        gate = GateConfig(metric="score", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.8})
        assert result.status == "PASS"

    def test_lte_pass_equal(self):
        gate = GateConfig(metric="pval", threshold=0.05, comparator="lte")
        result = evaluate_gate(gate, {"pval": 0.05})
        assert result.status == "PASS"

    def test_lte_pass_below(self):
        gate = GateConfig(metric="pval", threshold=0.05, comparator="lte")
        result = evaluate_gate(gate, {"pval": 0.01})
        assert result.status == "PASS"

    def test_gt_pass(self):
        gate = GateConfig(metric="delta", threshold=0.0, comparator="gt")
        result = evaluate_gate(gate, {"delta": 0.001})
        assert result.status == "PASS"

    def test_lt_pass(self):
        gate = GateConfig(metric="error", threshold=1.0, comparator="lt")
        result = evaluate_gate(gate, {"error": 0.5})
        assert result.status == "PASS"

    def test_eq_pass(self):
        gate = GateConfig(metric="count", threshold=100.0, comparator="eq")
        result = evaluate_gate(gate, {"count": 100.0})
        assert result.status == "PASS"


# --- evaluate_gate: FAIL cases ---


class TestEvaluateGateFail:
    def test_gte_fail(self):
        gate = GateConfig(metric="score", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.3})
        assert result.status == "FAIL"
        assert result.observed_value == 0.3

    def test_lte_fail(self):
        gate = GateConfig(metric="pval", threshold=0.05, comparator="lte")
        result = evaluate_gate(gate, {"pval": 0.1})
        assert result.status == "FAIL"

    def test_gt_fail_equal(self):
        gate = GateConfig(metric="delta", threshold=0.0, comparator="gt")
        result = evaluate_gate(gate, {"delta": 0.0})
        assert result.status == "FAIL"

    def test_lt_fail_equal(self):
        gate = GateConfig(metric="error", threshold=1.0, comparator="lt")
        result = evaluate_gate(gate, {"error": 1.0})
        assert result.status == "FAIL"

    def test_eq_fail(self):
        gate = GateConfig(metric="count", threshold=100.0, comparator="eq")
        result = evaluate_gate(gate, {"count": 99.0})
        assert result.status == "FAIL"


# --- evaluate_gate: SKIP ---


class TestEvaluateGateSkip:
    def test_missing_metric_returns_skip(self):
        gate = GateConfig(metric="nonexistent", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {"other_metric": 1.0})
        assert result.status == "SKIP"
        assert result.observed_value is None

    def test_skip_with_empty_metrics(self):
        gate = GateConfig(metric="score", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {})
        assert result.status == "SKIP"


# --- GateResult structure ---


class TestGateResult:
    def test_gate_result_fields(self):
        gate = GateConfig(metric="m", threshold=1.0, comparator="gte")
        r = GateResult(gate=gate, status="PASS", observed_value=1.5, message="ok")
        assert r.gate is gate
        assert r.status == "PASS"
        assert r.observed_value == 1.5
        assert r.message == "ok"

    def test_gate_result_message_present(self):
        gate = GateConfig(metric="score", threshold=0.5, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.8})
        assert isinstance(result.message, str)
        assert len(result.message) > 0


# --- evaluate_phase_gates ---


class TestEvaluatePhaseGates:
    def test_all_pass(self):
        gates = [
            GateConfig(metric="score", threshold=0.5, comparator="gte"),
            GateConfig(metric="pval", threshold=0.05, comparator="lte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {"score": 0.8, "pval": 0.01}
        report = evaluate_phase_gates(phase, metrics)

        assert isinstance(report, PhaseGateReport)
        assert report.phase_name == "p1"
        assert report.overall_pass is True
        assert len(report.results) == 2
        assert len(report.failures) == 0

    def test_one_fail_means_overall_fail(self):
        gates = [
            GateConfig(metric="score", threshold=0.5, comparator="gte"),
            GateConfig(metric="pval", threshold=0.05, comparator="lte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {"score": 0.8, "pval": 0.1}  # pval fails
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False
        assert len(report.failures) == 1
        assert report.failures[0].gate.metric == "pval"

    def test_all_fail(self):
        gates = [
            GateConfig(metric="score", threshold=0.5, comparator="gte"),
            GateConfig(metric="pval", threshold=0.05, comparator="lte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {"score": 0.1, "pval": 0.5}
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False
        assert len(report.failures) == 2

    def test_skip_does_not_cause_failure(self):
        """SKIP gates should not cause overall failure (metric just not available yet)."""
        gates = [
            GateConfig(metric="score", threshold=0.5, comparator="gte"),
            GateConfig(metric="missing_metric", threshold=1.0, comparator="gte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {"score": 0.8}
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is True
        assert len(report.failures) == 0
        # Verify the skip is still in results
        statuses = [r.status for r in report.results]
        assert "SKIP" in statuses

    def test_human_review_flag(self):
        gates = [GateConfig(metric="score", threshold=0.5, comparator="gte")]
        phase = PhaseConfig(
            name="p1",
            description="test phase",
            gates=gates,
            requires_human_review=True,
        )
        metrics = {"score": 0.8}
        report = evaluate_phase_gates(phase, metrics)

        assert report.requires_human_review is True

    def test_no_human_review_flag(self):
        gates = [GateConfig(metric="score", threshold=0.5, comparator="gte")]
        phase = PhaseConfig(
            name="p1",
            description="test phase",
            gates=gates,
            requires_human_review=False,
        )
        metrics = {"score": 0.8}
        report = evaluate_phase_gates(phase, metrics)

        assert report.requires_human_review is False

    def test_empty_gates_is_pass(self):
        """A phase with no gates should trivially pass."""
        phase = PhaseConfig(name="p1", description="no gates")
        report = evaluate_phase_gates(phase, {"score": 0.8})

        assert report.overall_pass is True
        assert len(report.results) == 0
        assert len(report.failures) == 0

    def test_all_skip_means_overall_fail(self):
        """If ALL gates are SKIP (no metrics found), phase should NOT pass."""
        gates = [
            GateConfig(metric="metric_a", threshold=0.5, comparator="gte"),
            GateConfig(metric="metric_b", threshold=1.0, comparator="gte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {}  # No metrics at all
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False
        # All results should be SKIP
        assert all(r.status == "SKIP" for r in report.results)

    def test_all_skip_with_unrelated_metrics_means_overall_fail(self):
        """If all GATE metrics are missing (even if dict has other keys), fail."""
        gates = [
            GateConfig(metric="metric_a", threshold=0.5, comparator="gte"),
        ]
        phase = PhaseConfig(name="p1", description="test phase", gates=gates)
        metrics = {"unrelated_metric": 0.9}  # Has data, but not for any gate
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False

    def test_failures_list_only_contains_fail_status(self):
        """The failures list should only contain FAIL results, not SKIP or PASS."""
        gates = [
            GateConfig(metric="pass_metric", threshold=0.5, comparator="gte"),
            GateConfig(metric="fail_metric", threshold=0.5, comparator="gte"),
            GateConfig(metric="skip_metric", threshold=0.5, comparator="gte"),
        ]
        phase = PhaseConfig(name="p1", description="mixed", gates=gates)
        metrics = {"pass_metric": 0.8, "fail_metric": 0.1}
        report = evaluate_phase_gates(phase, metrics)

        assert len(report.failures) == 1
        assert report.failures[0].gate.metric == "fail_metric"
        assert all(f.status == "FAIL" for f in report.failures)
