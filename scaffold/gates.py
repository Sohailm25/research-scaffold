# ABOUTME: Phase gate evaluation engine for the research scaffold.
# ABOUTME: Evaluates metric thresholds mechanically; the orchestrator decides, not the agent.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from scaffold.config import GateConfig, PhaseConfig

_COMPARATORS = {
    "gte": lambda obs, thr: obs >= thr,
    "lte": lambda obs, thr: obs <= thr,
    "gt": lambda obs, thr: obs > thr,
    "lt": lambda obs, thr: obs < thr,
    "eq": lambda obs, thr: obs == thr,
}


@dataclass
class GateResult:
    """Outcome of evaluating a single gate against observed metrics."""

    gate: GateConfig
    status: Literal["PASS", "FAIL", "SKIP", "ERROR"]
    observed_value: float | None
    message: str


@dataclass
class PhaseGateReport:
    """Aggregated gate results for a phase."""

    phase_name: str
    results: list[GateResult]
    overall_pass: bool
    requires_human_review: bool
    failures: list[GateResult] = field(default_factory=list)


def evaluate_gate(gate: GateConfig, metrics: dict[str, float]) -> GateResult:
    """Evaluate a single gate against a metrics dictionary.

    Returns SKIP if the metric is not present in the dict.
    Returns PASS/FAIL based on comparator logic.
    """
    if gate.metric not in metrics:
        return GateResult(
            gate=gate,
            status="SKIP",
            observed_value=None,
            message=f"Metric '{gate.metric}' not found in provided metrics",
        )

    observed = metrics[gate.metric]
    comparator_fn = _COMPARATORS[gate.comparator]
    passed = comparator_fn(observed, gate.threshold)

    status: Literal["PASS", "FAIL"] = "PASS" if passed else "FAIL"
    verb = "meets" if passed else "does not meet"
    message = (
        f"{gate.metric}={observed} {verb} threshold "
        f"{gate.comparator} {gate.threshold}"
    )

    return GateResult(
        gate=gate,
        status=status,
        observed_value=observed,
        message=message,
    )


def evaluate_phase_gates(
    phase: PhaseConfig, metrics: dict[str, float]
) -> PhaseGateReport:
    """Evaluate all gates for a phase and produce an aggregated report.

    A phase passes if no gate has status FAIL (SKIP does not cause failure).
    """
    results = [evaluate_gate(gate, metrics) for gate in phase.gates]
    failures = [r for r in results if r.status == "FAIL"]
    overall_pass = len(failures) == 0

    return PhaseGateReport(
        phase_name=phase.name,
        results=results,
        overall_pass=overall_pass,
        requires_human_review=phase.requires_human_review,
        failures=failures,
    )
