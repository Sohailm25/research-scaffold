# ABOUTME: Experiment configuration dataclasses and YAML loader for the research scaffold.
# ABOUTME: Defines typed schema for experiment configs and validates on load.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_COMPARATORS = frozenset({"gte", "lte", "gt", "lt", "eq"})

REQUIRED_TOP_LEVEL_FIELDS = (
    "name",
    "thesis",
    "research_question",
    "models",
    "hypotheses",
)


@dataclass
class ModelConfig:
    """Configuration for a single model (development, primary, or secondary)."""

    name: str
    purpose: str


@dataclass
class RuntimeConfig:
    """Runtime environment configuration with sensible defaults for local development."""

    python_env: str = ".venv"
    accelerator: str = "mps"
    fallback: str = "cpu"
    platform: str = "macbook_m4_128gb"


@dataclass
class GateConfig:
    """A single phase gate: metric + threshold + comparator."""

    metric: str
    threshold: float
    comparator: str

    def __post_init__(self) -> None:
        if self.comparator not in VALID_COMPARATORS:
            raise ValueError(
                f"Invalid comparator '{self.comparator}'. "
                f"Must be one of: {sorted(VALID_COMPARATORS)}"
            )


@dataclass
class PhaseConfig:
    """Configuration for a single experiment phase with gates and dependencies."""

    name: str
    description: str
    gates: list[GateConfig] = field(default_factory=list)
    requires_human_review: bool = False
    depends_on: list[str] = field(default_factory=list)


@dataclass
class HypothesesConfig:
    """Primary and secondary hypotheses for the experiment."""

    primary: str
    secondary: list[str] = field(default_factory=list)


@dataclass
class NullModelConfig:
    """A null model (baseline) for comparison."""

    name: str
    description: str = ""


@dataclass
class ModelsConfig:
    """Container for development, primary, and optional secondary models."""

    development: ModelConfig
    primary: ModelConfig
    secondary: ModelConfig | None = None


@dataclass
class ExperimentConfig:
    """Top-level experiment configuration loaded from YAML."""

    name: str
    thesis: str
    research_question: str
    models: ModelsConfig
    runtime: RuntimeConfig
    hypotheses: HypothesesConfig
    null_models: list[NullModelConfig]
    phases: list[PhaseConfig]
    required_lanes: list[str]
    statistics: dict
    framing_locks: list[str]
    guardrails: list[str]
    budget: float | None = None
    reproducibility: dict = field(default_factory=dict)


def _parse_gate(raw: dict) -> GateConfig:
    """Parse a raw dict into a GateConfig, validating comparator."""
    return GateConfig(
        metric=raw["metric"],
        threshold=float(raw["threshold"]),
        comparator=raw["comparator"],
    )


def _parse_phase(raw: dict) -> PhaseConfig:
    """Parse a raw dict into a PhaseConfig with nested GateConfigs."""
    gates = [_parse_gate(g) for g in raw.get("gates", [])]
    return PhaseConfig(
        name=raw["name"],
        description=raw["description"],
        gates=gates,
        requires_human_review=raw.get("requires_human_review", False),
        depends_on=raw.get("depends_on", []) or [],
    )


def _parse_model(raw: dict) -> ModelConfig:
    """Parse a raw dict into a ModelConfig."""
    return ModelConfig(name=raw["name"], purpose=raw["purpose"])


def _parse_null_model(raw: dict) -> NullModelConfig:
    """Parse a raw dict into a NullModelConfig."""
    if isinstance(raw, str):
        return NullModelConfig(name=raw)
    return NullModelConfig(name=raw["name"], description=raw.get("description", ""))


def load_config(path: Path) -> ExperimentConfig:
    """Load a YAML config file and parse it into an ExperimentConfig.

    Raises ValueError for missing required fields or invalid values.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError("Empty config file")

    # Handle nested experiment: {name, thesis} envelope from rendered templates
    if "experiment" in raw and isinstance(raw["experiment"], dict):
        exp_block = raw.pop("experiment")
        for key in ("name", "thesis"):
            if key in exp_block and key not in raw:
                raw[key] = exp_block[key]

    # Validate required top-level fields
    for field_name in REQUIRED_TOP_LEVEL_FIELDS:
        if field_name not in raw:
            raise ValueError(f"Missing required field: '{field_name}'")

    # Parse models
    models_raw = raw["models"]
    dev = _parse_model(models_raw["development"])
    pri = _parse_model(models_raw["primary"])
    sec = _parse_model(models_raw["secondary"]) if "secondary" in models_raw else None
    models = ModelsConfig(development=dev, primary=pri, secondary=sec)

    # Parse runtime
    runtime_raw = raw.get("runtime", {}) or {}
    runtime = RuntimeConfig(
        python_env=runtime_raw.get("python_env", ".venv"),
        accelerator=runtime_raw.get("accelerator", "mps"),
        fallback=runtime_raw.get("fallback", "cpu"),
        platform=runtime_raw.get("platform", "macbook_m4_128gb"),
    )

    # Parse hypotheses
    hyp_raw = raw["hypotheses"]
    secondary = hyp_raw.get("secondary", []) or []
    if isinstance(secondary, str):
        secondary = [secondary]
    hypotheses = HypothesesConfig(primary=hyp_raw["primary"], secondary=secondary)

    # Parse null models
    null_models_raw = raw.get("null_models", []) or []
    null_models = [_parse_null_model(nm) for nm in null_models_raw]

    # Parse phases
    phases_raw = raw.get("phases", []) or []
    phases = [_parse_phase(p) for p in phases_raw]

    # Budget
    budget_val = raw.get("budget")
    budget = float(budget_val) if budget_val is not None else None

    return ExperimentConfig(
        name=raw["name"],
        thesis=raw["thesis"],
        research_question=raw["research_question"],
        models=models,
        runtime=runtime,
        hypotheses=hypotheses,
        null_models=null_models,
        phases=phases,
        required_lanes=raw.get("required_lanes", []) or [],
        statistics=raw.get("statistics", {}) or {},
        framing_locks=raw.get("framing_locks", []) or [],
        guardrails=raw.get("guardrails", []) or [],
        budget=budget,
        reproducibility=raw.get("reproducibility", {}) or {},
    )
