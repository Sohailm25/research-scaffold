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


# --- Near-miss detection ---


class TestNearMissDetection:
    """Tests for near-miss detection on gate results."""

    def test_gte_near_miss_within_10_percent(self):
        """FAIL within 10% of threshold has near_miss=True (gte comparator)."""
        # threshold=0.65, margin=0.065, near miss if observed >= 0.585
        gate = GateConfig(metric="score", threshold=0.65, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.6085})
        assert result.status == "FAIL"
        assert result.near_miss is True

    def test_gte_far_miss_not_near(self):
        """FAIL far from threshold has near_miss=False (gte comparator)."""
        gate = GateConfig(metric="score", threshold=0.65, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.1})
        assert result.status == "FAIL"
        assert result.near_miss is False

    def test_pass_never_near_miss(self):
        """PASS results always have near_miss=False."""
        gate = GateConfig(metric="score", threshold=0.65, comparator="gte")
        result = evaluate_gate(gate, {"score": 0.8})
        assert result.status == "PASS"
        assert result.near_miss is False

    def test_skip_never_near_miss(self):
        """SKIP results always have near_miss=False."""
        gate = GateConfig(metric="score", threshold=0.65, comparator="gte")
        result = evaluate_gate(gate, {"other": 0.6})
        assert result.status == "SKIP"
        assert result.near_miss is False

    def test_lte_near_miss(self):
        """FAIL within 10% of threshold has near_miss=True (lte comparator)."""
        # threshold=0.25, margin=0.025, near miss if observed <= 0.275
        gate = GateConfig(metric="pval", threshold=0.25, comparator="lte")
        result = evaluate_gate(gate, {"pval": 0.27})
        assert result.status == "FAIL"
        assert result.near_miss is True

    def test_lte_far_miss(self):
        """FAIL far from threshold has near_miss=False (lte comparator)."""
        gate = GateConfig(metric="pval", threshold=0.25, comparator="lte")
        result = evaluate_gate(gate, {"pval": 0.5})
        assert result.status == "FAIL"
        assert result.near_miss is False

    def test_zero_threshold_uses_minimum_margin(self):
        """Threshold of 0 uses minimum margin of 0.01."""
        # threshold=0.0, margin=max(0.0*0.1, 0.01)=0.01
        # gt comparator: near miss if observed >= 0.0 - 0.01 = -0.01
        gate = GateConfig(metric="delta", threshold=0.0, comparator="gt")
        result = evaluate_gate(gate, {"delta": 0.0})
        assert result.status == "FAIL"
        assert result.near_miss is True

    def test_eq_near_miss(self):
        """FAIL within 10% of threshold has near_miss=True (eq comparator)."""
        # threshold=100.0, margin=10.0, near miss if abs(observed - 100) <= 10
        gate = GateConfig(metric="count", threshold=100.0, comparator="eq")
        result = evaluate_gate(gate, {"count": 95.0})
        assert result.status == "FAIL"
        assert result.near_miss is True

    def test_eq_far_miss(self):
        """FAIL far from threshold has near_miss=False (eq comparator)."""
        gate = GateConfig(metric="count", threshold=100.0, comparator="eq")
        result = evaluate_gate(gate, {"count": 50.0})
        assert result.status == "FAIL"
        assert result.near_miss is False

    def test_gt_near_miss(self):
        """FAIL within margin for gt comparator has near_miss=True."""
        # threshold=1.0, margin=0.1, near miss if observed >= 0.9
        gate = GateConfig(metric="delta", threshold=1.0, comparator="gt")
        result = evaluate_gate(gate, {"delta": 1.0})
        assert result.status == "FAIL"
        assert result.near_miss is True

    def test_lt_near_miss(self):
        """FAIL within margin for lt comparator has near_miss=True."""
        # threshold=1.0, margin=0.1, near miss if observed <= 1.1
        gate = GateConfig(metric="error", threshold=1.0, comparator="lt")
        result = evaluate_gate(gate, {"error": 1.0})
        assert result.status == "FAIL"
        assert result.near_miss is True


class TestPhaseGateReportNearMisses:
    """Tests for near_misses list on PhaseGateReport."""

    def test_near_misses_list_populated(self):
        """PhaseGateReport.near_misses contains only near-miss FAIL results."""
        gates = [
            GateConfig(metric="close_metric", threshold=0.65, comparator="gte"),
            GateConfig(metric="far_metric", threshold=0.65, comparator="gte"),
        ]
        phase = PhaseConfig(name="p1", description="test", gates=gates)
        # close_metric=0.6085 is within 10%, far_metric=0.1 is not
        metrics = {"close_metric": 0.6085, "far_metric": 0.1}
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False
        assert len(report.near_misses) == 1
        assert report.near_misses[0].gate.metric == "close_metric"

    def test_near_misses_empty_when_all_pass(self):
        """PhaseGateReport.near_misses is empty when all gates pass."""
        gates = [GateConfig(metric="score", threshold=0.5, comparator="gte")]
        phase = PhaseConfig(name="p1", description="test", gates=gates)
        metrics = {"score": 0.8}
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is True
        assert len(report.near_misses) == 0

    def test_near_misses_empty_when_all_far_fails(self):
        """PhaseGateReport.near_misses is empty when all fails are far misses."""
        gates = [GateConfig(metric="score", threshold=0.65, comparator="gte")]
        phase = PhaseConfig(name="p1", description="test", gates=gates)
        metrics = {"score": 0.1}
        report = evaluate_phase_gates(phase, metrics)

        assert report.overall_pass is False
        assert len(report.near_misses) == 0
