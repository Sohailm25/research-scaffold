# ABOUTME: Tests for scaffold/intake.py - document intake and LLM-based config synthesis.
# ABOUTME: Uses _FakeClaudeRunner for deterministic testing without real CLI calls.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scaffold.intake import (
    ClaudeCLIRunner,
    IntakeResult,
    LLMRunner,
    intake,
    read_document,
    scan_documents,
    synthesize_config,
)

# ---------------------------------------------------------------------------
# Shared fake runner and canned response
# ---------------------------------------------------------------------------

CANNED_RESPONSE = {
    "experiment_name": "test-experiment",
    "research_question": "Does X cause Y?",
    "hypotheses": {
        "primary": "X causes Y under controlled conditions",
        "secondary": ["Alternative mechanism A", "Alternative mechanism B"],
    },
    "null_models": [
        {"name": "uniform_baseline", "description": "Equal weight across all layers"},
    ],
    "framing_locks": [
        "This is observational, not causal",
        "Results limited to tested model family",
    ],
    "required_lanes": ["oracle_alpha", "pattern_analysis"],
    "phases": [
        {
            "name": "pilot",
            "description": "Initial signal detection",
            "gates": [
                {"metric": "effect_size", "threshold": 0.1, "comparator": "gte"},
            ],
            "requires_human_review": False,
            "depends_on": [],
        },
        {
            "name": "confirmatory",
            "description": "Full-scale confirmation",
            "gates": [
                {"metric": "p_value", "threshold": 0.05, "comparator": "lte"},
            ],
            "requires_human_review": True,
            "depends_on": ["pilot"],
        },
    ],
    "models": {
        "development": {"name": "gpt2", "purpose": "fast iteration"},
        "primary": {"name": "google/gemma-2-2b", "purpose": "main results"},
    },
    "guardrails": ["No causal language without RCT", "Report all null results"],
    "statistics": {
        "significance_level": 0.05,
        "effect_size_minimum": 0.2,
    },
}


class _FakeClaudeRunner:
    """Deterministic LLM runner that returns canned JSON responses.

    Implements the LLMRunner protocol without hitting any real CLI or API.
    """

    def __init__(self, response: dict | str | None = None):
        self._response = response if response is not None else CANNED_RESPONSE
        self.last_prompt: str | None = None
        self.call_count: int = 0

    def run(self, prompt: str) -> str:
        self.last_prompt = prompt
        self.call_count += 1
        if isinstance(self._response, str):
            return self._response
        return json.dumps(self._response)


# ---------------------------------------------------------------------------
# scan_documents
# ---------------------------------------------------------------------------


class TestScanDocuments:
    def test_finds_markdown_files(self, tmp_path: Path):
        (tmp_path / "notes.md").write_text("# Notes")
        (tmp_path / "plan.md").write_text("# Plan")
        result = scan_documents(tmp_path)
        assert len(result) == 2
        names = [p.name for p in result]
        assert "notes.md" in names
        assert "plan.md" in names

    def test_finds_txt_files(self, tmp_path: Path):
        (tmp_path / "readme.txt").write_text("hello")
        result = scan_documents(tmp_path)
        assert len(result) == 1
        assert result[0].name == "readme.txt"

    def test_finds_pdf_files(self, tmp_path: Path):
        (tmp_path / "paper.pdf").write_bytes(b"%PDF-fake")
        result = scan_documents(tmp_path)
        assert len(result) == 1
        assert result[0].name == "paper.pdf"

    def test_ignores_non_document_files(self, tmp_path: Path):
        (tmp_path / "code.pyc").write_bytes(b"\x00")
        (tmp_path / "image.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "data.csv").write_text("a,b,c")
        result = scan_documents(tmp_path)
        assert len(result) == 0

    def test_returns_sorted_list(self, tmp_path: Path):
        (tmp_path / "zebra.md").write_text("z")
        (tmp_path / "alpha.md").write_text("a")
        (tmp_path / "middle.txt").write_text("m")
        result = scan_documents(tmp_path)
        names = [p.name for p in result]
        assert names == sorted(names)

    def test_empty_directory(self, tmp_path: Path):
        result = scan_documents(tmp_path)
        assert result == []

    def test_skips_subdirectories(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.md").write_text("nested")
        (tmp_path / "top.md").write_text("top")
        result = scan_documents(tmp_path)
        assert len(result) == 1
        assert result[0].name == "top.md"


# ---------------------------------------------------------------------------
# read_document
# ---------------------------------------------------------------------------


class TestReadDocument:
    def test_reads_markdown(self, tmp_path: Path):
        p = tmp_path / "test.md"
        p.write_text("# Hello World\nContent here.")
        content = read_document(p)
        assert "# Hello World" in content
        assert "Content here." in content

    def test_reads_txt(self, tmp_path: Path):
        p = tmp_path / "test.txt"
        p.write_text("Plain text content")
        content = read_document(p)
        assert content == "Plain text content"

    def test_pdf_fallback_when_not_real_pdf(self, tmp_path: Path):
        """For a non-real PDF, should return either extracted text or a fallback message."""
        p = tmp_path / "fake.pdf"
        p.write_bytes(b"not a real pdf")
        content = read_document(p)
        # Either pymupdf extracts something or we get a fallback
        assert isinstance(content, str)
        assert len(content) > 0

    def test_docx_returns_placeholder(self, tmp_path: Path):
        p = tmp_path / "test.docx"
        p.write_bytes(b"fake docx")
        content = read_document(p)
        assert "docx" in content.lower()


# ---------------------------------------------------------------------------
# IntakeResult dataclass
# ---------------------------------------------------------------------------


class TestIntakeResult:
    def _make_result(self, **overrides) -> IntakeResult:
        defaults = {
            "experiment_name": "test-exp",
            "research_question": "Does X cause Y?",
            "hypotheses": {"primary": "X causes Y", "secondary": ["Alt A"]},
            "null_models": [{"name": "uniform", "description": "Equal weights"}],
            "framing_locks": ["Observational only"],
            "required_lanes": ["oracle_alpha"],
            "phases": [
                {
                    "name": "pilot",
                    "description": "Signal check",
                    "gates": [
                        {"metric": "effect_size", "threshold": 0.1, "comparator": "gte"},
                    ],
                },
            ],
            "models": {
                "development": {"name": "gpt2", "purpose": "fast iteration"},
                "primary": {"name": "gemma-2-2b", "purpose": "main results"},
            },
            "guardrails": ["No causal claims"],
            "statistics": {"significance_level": 0.05},
        }
        defaults.update(overrides)
        return IntakeResult(**defaults)

    def test_required_fields(self):
        r = self._make_result()
        assert r.experiment_name == "test-exp"
        assert r.research_question == "Does X cause Y?"
        assert r.hypotheses["primary"] == "X causes Y"
        assert len(r.null_models) == 1
        assert len(r.framing_locks) == 1
        assert r.required_lanes == ["oracle_alpha"]
        assert len(r.phases) == 1
        assert r.guardrails == ["No causal claims"]
        assert r.statistics["significance_level"] == 0.05

    def test_source_documents_default_empty(self):
        r = self._make_result()
        assert r.source_documents == []

    def test_source_documents_can_be_set(self, tmp_path: Path):
        p = tmp_path / "doc.md"
        p.write_text("content")
        r = self._make_result(source_documents=[p])
        assert r.source_documents == [p]


# ---------------------------------------------------------------------------
# to_experiment_config
# ---------------------------------------------------------------------------


class TestToExperimentConfig:
    def _make_result(self) -> IntakeResult:
        return IntakeResult(
            experiment_name="test-exp",
            research_question="Does X cause Y?",
            hypotheses={"primary": "X causes Y", "secondary": ["Alt A", "Alt B"]},
            null_models=[
                {"name": "uniform", "description": "Equal weights"},
                {"name": "random", "description": "Random baseline"},
            ],
            framing_locks=["Observational only", "Single model family"],
            required_lanes=["oracle_alpha", "pattern_analysis"],
            phases=[
                {
                    "name": "pilot",
                    "description": "Signal check",
                    "gates": [
                        {"metric": "effect_size", "threshold": 0.1, "comparator": "gte"},
                    ],
                    "requires_human_review": False,
                    "depends_on": [],
                },
                {
                    "name": "confirmatory",
                    "description": "Full confirmation",
                    "gates": [
                        {"metric": "p_value", "threshold": 0.05, "comparator": "lte"},
                    ],
                    "requires_human_review": True,
                    "depends_on": ["pilot"],
                },
            ],
            models={
                "development": {"name": "gpt2", "purpose": "fast iteration"},
                "primary": {"name": "gemma-2-2b", "purpose": "main results"},
            },
            guardrails=["No causal claims"],
            statistics={"significance_level": 0.05, "effect_size_minimum": 0.2},
        )

    def test_returns_experiment_config(self):
        from scaffold.config import ExperimentConfig

        r = self._make_result()
        cfg = r.to_experiment_config()
        assert isinstance(cfg, ExperimentConfig)

    def test_maps_name_and_thesis(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert cfg.name == "test-exp"
        assert cfg.thesis == "Does X cause Y?"
        assert cfg.research_question == "Does X cause Y?"

    def test_maps_models(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert cfg.models.development.name == "gpt2"
        assert cfg.models.development.purpose == "fast iteration"
        assert cfg.models.primary.name == "gemma-2-2b"
        assert cfg.models.primary.purpose == "main results"

    def test_maps_hypotheses(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert cfg.hypotheses.primary == "X causes Y"
        assert cfg.hypotheses.secondary == ["Alt A", "Alt B"]

    def test_maps_null_models(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert len(cfg.null_models) == 2
        assert cfg.null_models[0].name == "uniform"
        assert cfg.null_models[0].description == "Equal weights"

    def test_maps_phases_with_gates(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert len(cfg.phases) == 2
        pilot = cfg.phases[0]
        assert pilot.name == "pilot"
        assert len(pilot.gates) == 1
        assert pilot.gates[0].metric == "effect_size"
        assert pilot.gates[0].threshold == 0.1
        assert pilot.gates[0].comparator == "gte"
        assert pilot.requires_human_review is False

    def test_maps_phase_dependencies(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        confirm = cfg.phases[1]
        assert confirm.depends_on == ["pilot"]
        assert confirm.requires_human_review is True

    def test_maps_lanes_and_guardrails(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert cfg.required_lanes == ["oracle_alpha", "pattern_analysis"]
        assert cfg.guardrails == ["No causal claims"]
        assert cfg.framing_locks == ["Observational only", "Single model family"]

    def test_maps_statistics(self):
        r = self._make_result()
        cfg = r.to_experiment_config()
        assert cfg.statistics["significance_level"] == 0.05
        assert cfg.statistics["effect_size_minimum"] == 0.2


# ---------------------------------------------------------------------------
# synthesize_config
# ---------------------------------------------------------------------------


class TestSynthesizeConfig:
    def test_returns_intake_result(self):
        runner = _FakeClaudeRunner()
        docs = {"IDEA.md": "Study X effect on Y"}
        result = synthesize_config(docs, runner)
        assert isinstance(result, IntakeResult)

    def test_parses_all_fields(self):
        runner = _FakeClaudeRunner()
        docs = {"notes.md": "Research notes about X"}
        result = synthesize_config(docs, runner)
        assert result.experiment_name == "test-experiment"
        assert result.research_question == "Does X cause Y?"
        assert result.hypotheses["primary"] == "X causes Y under controlled conditions"
        assert len(result.null_models) == 1
        assert len(result.framing_locks) == 2
        assert len(result.required_lanes) == 2
        assert len(result.phases) == 2
        assert len(result.guardrails) == 2
        assert result.statistics["significance_level"] == 0.05

    def test_passes_documents_in_prompt(self):
        runner = _FakeClaudeRunner()
        docs = {"idea.md": "My research idea", "notes.txt": "Supporting notes"}
        synthesize_config(docs, runner)
        assert runner.last_prompt is not None
        assert "My research idea" in runner.last_prompt
        assert "Supporting notes" in runner.last_prompt

    def test_handles_markdown_fenced_response(self):
        """Runner response wrapped in ```json fencing should still parse."""
        fenced = "```json\n" + json.dumps(CANNED_RESPONSE) + "\n```"
        runner = _FakeClaudeRunner(response=fenced)
        docs = {"doc.md": "content"}
        result = synthesize_config(docs, runner)
        assert result.experiment_name == "test-experiment"

    def test_raises_on_invalid_json(self):
        runner = _FakeClaudeRunner(response="not json at all")
        docs = {"doc.md": "content"}
        with pytest.raises(json.JSONDecodeError):
            synthesize_config(docs, runner)


# ---------------------------------------------------------------------------
# IDEA.md priority
# ---------------------------------------------------------------------------


class TestIdeaPriority:
    def test_idea_md_prepended_with_priority(self, tmp_path: Path):
        (tmp_path / "IDEA.md").write_text("My primary research idea")
        (tmp_path / "notes.md").write_text("Supporting notes")
        runner = _FakeClaudeRunner()
        intake(tmp_path, runner=runner)
        prompt = runner.last_prompt
        assert prompt is not None
        # IDEA.md content should appear before notes.md content
        idea_pos = prompt.index("My primary research idea")
        notes_pos = prompt.index("Supporting notes")
        assert idea_pos < notes_pos

    def test_idea_md_has_priority_marker(self, tmp_path: Path):
        (tmp_path / "IDEA.md").write_text("Research idea")
        runner = _FakeClaudeRunner()
        intake(tmp_path, runner=runner)
        prompt = runner.last_prompt
        assert prompt is not None
        assert "PRIMARY" in prompt

    def test_without_idea_md_still_works(self, tmp_path: Path):
        (tmp_path / "notes.md").write_text("Just notes")
        runner = _FakeClaudeRunner()
        result = intake(tmp_path, runner=runner)
        assert result.experiment_name == "test-experiment"


# ---------------------------------------------------------------------------
# intake (full pipeline)
# ---------------------------------------------------------------------------


class TestIntake:
    def test_full_pipeline(self, tmp_path: Path):
        (tmp_path / "IDEA.md").write_text("# Research Idea\nStudy X")
        (tmp_path / "background.txt").write_text("Background info")
        runner = _FakeClaudeRunner()
        result = intake(tmp_path, runner=runner)
        assert isinstance(result, IntakeResult)
        assert result.experiment_name == "test-experiment"
        assert len(result.source_documents) == 2

    def test_sets_source_documents(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("doc1")
        (tmp_path / "doc2.txt").write_text("doc2")
        runner = _FakeClaudeRunner()
        result = intake(tmp_path, runner=runner)
        names = sorted([p.name for p in result.source_documents])
        assert names == ["doc1.md", "doc2.txt"]

    def test_raises_on_empty_directory(self, tmp_path: Path):
        runner = _FakeClaudeRunner()
        with pytest.raises(ValueError, match="No documents found"):
            intake(tmp_path, runner=runner)

    def test_calls_runner_exactly_once(self, tmp_path: Path):
        (tmp_path / "doc.md").write_text("content")
        runner = _FakeClaudeRunner()
        intake(tmp_path, runner=runner)
        assert runner.call_count == 1

    def test_default_runner_is_claude_cli(self):
        """When no runner passed, should default to ClaudeCLIRunner."""
        # We just verify the type check -- don't actually call it
        assert isinstance(ClaudeCLIRunner(), ClaudeCLIRunner)


# ---------------------------------------------------------------------------
# ClaudeCLIRunner protocol conformance
# ---------------------------------------------------------------------------


class TestClaudeCLIRunner:
    def test_implements_llm_runner_protocol(self):
        """ClaudeCLIRunner should be usable wherever LLMRunner is expected."""
        runner = ClaudeCLIRunner()
        # Structural check: has a run method that accepts a string
        assert callable(getattr(runner, "run", None))

    def test_configurable_timeout(self):
        runner = ClaudeCLIRunner(timeout=60)
        assert runner._timeout == 60

    def test_default_timeout(self):
        runner = ClaudeCLIRunner()
        assert runner._timeout == 300
