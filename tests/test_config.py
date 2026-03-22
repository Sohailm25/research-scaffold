# ABOUTME: Tests for scaffold/config.py - ExperimentConfig schema and YAML loader.
# ABOUTME: Covers dataclass construction, YAML loading, validation, defaults, and error cases.

from pathlib import Path

import pytest
import yaml

from scaffold.config import (
    ExperimentConfig,
    GateConfig,
    HypothesesConfig,
    ModelConfig,
    ModelsConfig,
    NullModelConfig,
    PhaseConfig,
    RuntimeConfig,
    load_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINIMAL_CONFIG = FIXTURES_DIR / "minimal_config.yaml"


# --- ModelConfig ---


class TestModelConfig:
    def test_create(self):
        m = ModelConfig(name="gpt2", purpose="fast_iteration")
        assert m.name == "gpt2"
        assert m.purpose == "fast_iteration"


# --- RuntimeConfig ---


class TestRuntimeConfig:
    def test_defaults(self):
        r = RuntimeConfig()
        assert r.python_env == ".venv"
        assert r.accelerator == "mps"
        assert r.fallback == "cpu"
        assert r.platform == "macbook_m4_128gb"

    def test_override(self):
        r = RuntimeConfig(accelerator="cuda", platform="a100_node")
        assert r.accelerator == "cuda"
        assert r.platform == "a100_node"


# --- GateConfig ---


class TestGateConfig:
    def test_valid_comparators(self):
        for comp in ("gte", "lte", "gt", "lt", "eq"):
            g = GateConfig(metric="test_metric", threshold=0.5, comparator=comp)
            assert g.comparator == comp

    def test_invalid_comparator_raises(self):
        with pytest.raises(ValueError, match="comparator"):
            GateConfig(metric="test_metric", threshold=0.5, comparator="invalid")


# --- PhaseConfig ---


class TestPhaseConfig:
    def test_defaults(self):
        gate = GateConfig(metric="m", threshold=1.0, comparator="gte")
        p = PhaseConfig(name="p1", description="desc", gates=[gate])
        assert p.requires_human_review is False
        assert p.depends_on == []

    def test_with_dependencies(self):
        gate = GateConfig(metric="m", threshold=1.0, comparator="gte")
        p = PhaseConfig(
            name="p2",
            description="desc",
            gates=[gate],
            requires_human_review=True,
            depends_on=["p1"],
        )
        assert p.requires_human_review is True
        assert p.depends_on == ["p1"]


# --- HypothesesConfig ---


class TestHypothesesConfig:
    def test_primary_only(self):
        h = HypothesesConfig(primary="Main hypothesis")
        assert h.primary == "Main hypothesis"
        assert h.secondary == []

    def test_with_secondary(self):
        h = HypothesesConfig(primary="Main", secondary=["S1", "S2"])
        assert len(h.secondary) == 2


# --- NullModelConfig ---


class TestNullModelConfig:
    def test_default_description(self):
        n = NullModelConfig(name="uniform")
        assert n.name == "uniform"
        assert n.description == ""

    def test_with_description(self):
        n = NullModelConfig(name="uniform", description="Equal weights")
        assert n.description == "Equal weights"


# --- ModelsConfig ---


class TestModelsConfig:
    def test_without_secondary(self):
        dev = ModelConfig(name="gpt2", purpose="dev")
        pri = ModelConfig(name="gemma", purpose="main")
        mc = ModelsConfig(development=dev, primary=pri)
        assert mc.secondary is None

    def test_with_secondary(self):
        dev = ModelConfig(name="gpt2", purpose="dev")
        pri = ModelConfig(name="gemma", purpose="main")
        sec = ModelConfig(name="pythia", purpose="dynamics")
        mc = ModelsConfig(development=dev, primary=pri, secondary=sec)
        assert mc.secondary.name == "pythia"


# --- ExperimentConfig ---


class TestExperimentConfig:
    def test_budget_none_default(self):
        """Budget should default to None if not provided."""
        cfg = ExperimentConfig(
            name="test",
            thesis="t",
            research_question="q",
            models=ModelsConfig(
                development=ModelConfig(name="gpt2", purpose="dev"),
                primary=ModelConfig(name="gemma", purpose="main"),
            ),
            runtime=RuntimeConfig(),
            hypotheses=HypothesesConfig(primary="h"),
            null_models=[],
            phases=[],
            required_lanes=[],
            statistics={},
            framing_locks=[],
            guardrails=[],
        )
        assert cfg.budget is None
        assert cfg.reproducibility == {}


# --- load_config ---


class TestLoadConfig:
    def test_load_minimal_config(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert isinstance(cfg, ExperimentConfig)
        assert cfg.name == "test-experiment"
        assert cfg.thesis == "test_thesis_statement"
        assert cfg.research_question == "Does X cause Y?"

    def test_models_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.models.development.name == "gpt2"
        assert cfg.models.primary.name == "google/gemma-2-2b"
        assert cfg.models.secondary is None

    def test_runtime_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.runtime.python_env == ".venv"
        assert cfg.runtime.accelerator == "mps"
        assert cfg.runtime.platform == "macbook_m4_128gb"

    def test_hypotheses_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert "depth-routing" in cfg.hypotheses.primary
        assert len(cfg.hypotheses.secondary) == 2

    def test_null_models_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert len(cfg.null_models) == 2
        assert cfg.null_models[0].name == "uniform"
        assert cfg.null_models[1].name == "random_dirichlet"

    def test_phases_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert len(cfg.phases) == 2
        p1 = cfg.phases[0]
        assert p1.name == "phase1_oracle_alpha"
        assert len(p1.gates) == 2
        assert p1.gates[0].metric == "cross_entropy_delta_nats"
        assert p1.gates[0].threshold == 0.01
        assert p1.gates[0].comparator == "gte"
        assert p1.requires_human_review is False

    def test_phase_dependencies(self):
        cfg = load_config(MINIMAL_CONFIG)
        p2 = cfg.phases[1]
        assert p2.depends_on == ["phase1_oracle_alpha"]
        assert p2.requires_human_review is True

    def test_required_lanes(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.required_lanes == ["oracle_alpha", "pattern_analysis"]

    def test_statistics_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.statistics["clustering_distance"] == "jensen_shannon_divergence"
        assert cfg.statistics["report_effect_sizes"] is True

    def test_framing_locks_and_guardrails(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert len(cfg.framing_locks) == 2
        assert len(cfg.guardrails) == 2

    def test_budget_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.budget == 50.0

    def test_reproducibility_loaded(self):
        cfg = load_config(MINIMAL_CONFIG)
        assert cfg.reproducibility["prereg_publication_target"] == "local_only"

    def test_missing_required_field_raises(self):
        """A config missing 'name' should raise ValueError."""
        import tempfile

        import yaml

        bad_config = {
            # "name" is missing
            "thesis": "t",
            "research_question": "q",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
            },
            "runtime": {},
            "hypotheses": {"primary": "h"},
            "null_models": [],
            "phases": [],
            "required_lanes": [],
            "statistics": {},
            "framing_locks": [],
            "guardrails": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(bad_config, f)
            f.flush()
            with pytest.raises(ValueError, match="name"):
                load_config(Path(f.name))

    def test_missing_models_raises(self):
        """A config missing 'models' should raise ValueError."""
        import tempfile

        import yaml

        bad_config = {
            "name": "test",
            "thesis": "t",
            "research_question": "q",
            # "models" is missing
            "runtime": {},
            "hypotheses": {"primary": "h"},
            "null_models": [],
            "phases": [],
            "required_lanes": [],
            "statistics": {},
            "framing_locks": [],
            "guardrails": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(bad_config, f)
            f.flush()
            with pytest.raises(ValueError, match="models"):
                load_config(Path(f.name))

    def test_invalid_comparator_in_yaml_raises(self):
        """A gate with invalid comparator in YAML should raise ValueError."""
        import tempfile

        import yaml

        bad_config = {
            "name": "test",
            "thesis": "t",
            "research_question": "q",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
            },
            "runtime": {},
            "hypotheses": {"primary": "h"},
            "null_models": [],
            "phases": [
                {
                    "name": "p1",
                    "description": "d",
                    "gates": [
                        {"metric": "m", "threshold": 1.0, "comparator": "BOGUS"},
                    ],
                },
            ],
            "required_lanes": [],
            "statistics": {},
            "framing_locks": [],
            "guardrails": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(bad_config, f)
            f.flush()
            with pytest.raises(ValueError, match="comparator"):
                load_config(Path(f.name))

    def test_config_without_budget(self):
        """Config without budget field should default to None."""
        import tempfile

        import yaml

        config = {
            "name": "test",
            "thesis": "t",
            "research_question": "q",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
            },
            "runtime": {},
            "hypotheses": {"primary": "h"},
            "null_models": [],
            "phases": [],
            "required_lanes": [],
            "statistics": {},
            "framing_locks": [],
            "guardrails": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            cfg = load_config(Path(f.name))
            assert cfg.budget is None
            assert cfg.reproducibility == {}

    def test_config_with_secondary_model(self):
        """Config with secondary model should load it correctly."""
        import tempfile

        import yaml

        config = {
            "name": "test",
            "thesis": "t",
            "research_question": "q",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
                "secondary": {"name": "pythia", "purpose": "dynamics"},
            },
            "runtime": {},
            "hypotheses": {"primary": "h"},
            "null_models": [],
            "phases": [],
            "required_lanes": [],
            "statistics": {},
            "framing_locks": [],
            "guardrails": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            cfg = load_config(Path(f.name))
            assert cfg.models.secondary is not None
            assert cfg.models.secondary.name == "pythia"


class TestNestedExperimentEnvelope:
    """Tests for configs using the experiment: {name, thesis} envelope format."""

    def test_load_nested_format(self, tmp_path):
        """Config with experiment: {name, thesis} envelope loads correctly."""
        config = {
            "experiment": {"name": "nested-exp", "thesis": "test thesis"},
            "research_question": "Does X work?",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
            },
            "hypotheses": {"primary": "X works"},
            "phases": [],
        }
        config_path = tmp_path / "nested.yaml"
        config_path.write_text(yaml.dump(config))
        cfg = load_config(config_path)
        assert cfg.name == "nested-exp"
        assert cfg.thesis == "test thesis"

    def test_flat_format_still_works(self, tmp_path):
        """Original flat format without experiment: envelope still works."""
        config = {
            "name": "flat-exp",
            "thesis": "flat thesis",
            "research_question": "Does Y work?",
            "models": {
                "development": {"name": "gpt2", "purpose": "dev"},
                "primary": {"name": "gemma", "purpose": "main"},
            },
            "hypotheses": {"primary": "Y works"},
            "phases": [],
        }
        config_path = tmp_path / "flat.yaml"
        config_path.write_text(yaml.dump(config))
        cfg = load_config(config_path)
        assert cfg.name == "flat-exp"
        assert cfg.thesis == "flat thesis"
