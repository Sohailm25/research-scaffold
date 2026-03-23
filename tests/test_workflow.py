# ABOUTME: Tests for scaffold/workflow.py - WORKFLOW.md loader and prompt renderer.
# ABOUTME: Covers YAML frontmatter parsing, prompt body extraction, and Jinja2 rendering.

import textwrap
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from scaffold.workflow import WorkflowConfig, load_workflow, render_prompt


class TestLoadWorkflow:
    def test_parse_yaml_frontmatter(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text(textwrap.dedent("""\
            ---
            runtime:
              python_env: .venv
              accelerator: mps
            agent:
              backend: claude
              model: claude-opus-4
            hooks:
              pre_run: bd prime
              post_run: bd sync
            ---

            # Hello
        """))
        config = load_workflow(wf)
        assert config.runtime == {"python_env": ".venv", "accelerator": "mps"}
        assert config.agent == {"backend": "claude", "model": "claude-opus-4"}
        assert config.hooks == {"pre_run": "bd prime", "post_run": "bd sync"}

    def test_parse_prompt_body(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text(textwrap.dedent("""\
            ---
            runtime: {}
            ---

            # The Prompt Body

            Execute {{ phase }} in {{ lane }}.
        """))
        config = load_workflow(wf)
        assert "# The Prompt Body" in config.prompt_template
        assert "{{ phase }}" in config.prompt_template
        assert "{{ lane }}" in config.prompt_template

    def test_no_frontmatter_raises(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text("# Just markdown, no frontmatter\n\nSome content.\n")
        with pytest.raises(ValueError, match="frontmatter"):
            load_workflow(wf)

    def test_empty_frontmatter(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text(textwrap.dedent("""\
            ---
            ---

            # Body content
        """))
        config = load_workflow(wf)
        assert config.runtime == {}
        assert config.agent == {}
        assert config.hooks == {}
        assert "# Body content" in config.prompt_template

    def test_frontmatter_with_extra_keys(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text(textwrap.dedent("""\
            ---
            runtime:
              python_env: .venv
            agent:
              backend: claude
            hooks:
              pre_run: echo hi
            custom_key: custom_value
            ---

            # Body
        """))
        config = load_workflow(wf)
        assert config.runtime == {"python_env": ".venv"}
        assert config.agent == {"backend": "claude"}
        assert config.hooks == {"pre_run": "echo hi"}
        # Extra keys are NOT in runtime/agent/hooks - they're just ignored
        # (the spec says "unknown keys preserved in appropriate section"
        # but custom_key is top-level, not nested under any section)

    def test_multiline_hooks(self, tmp_path):
        wf = tmp_path / "WORKFLOW.md"
        wf.write_text(textwrap.dedent("""\
            ---
            runtime: {}
            agent: {}
            hooks:
              pre_run: |
                echo "step 1"
                echo "step 2"
              post_run: bd sync
            ---

            # Body
        """))
        config = load_workflow(wf)
        assert "step 1" in config.hooks["pre_run"]
        assert "step 2" in config.hooks["pre_run"]
        assert config.hooks["post_run"] == "bd sync"


class TestRenderPrompt:
    def _make_workflow(self, template: str) -> WorkflowConfig:
        return WorkflowConfig(
            runtime={},
            agent={},
            hooks={},
            prompt_template=template,
        )

    def test_render_with_phase_lane_task(self):
        wf = self._make_workflow("Phase: {{ phase }}, Lane: {{ lane }}, Task: {{ task }}")
        result = render_prompt(wf, {"phase": "pilot", "lane": "oracle", "task": "run analysis"})
        assert result == "Phase: pilot, Lane: oracle, Task: run analysis"

    def test_render_with_missing_variable_uses_empty(self):
        wf = self._make_workflow("Phase: {{ phase }}, Lane: {{ lane }}")
        result = render_prompt(wf, {"phase": "pilot"})
        assert result == "Phase: pilot, Lane: "

    def test_render_preserves_markdown(self):
        template = "# Title\n\n**Bold** and *italic*\n\n- item 1\n- item 2\n"
        wf = self._make_workflow(template)
        result = render_prompt(wf, {})
        assert "# Title" in result
        assert "**Bold**" in result
        assert "- item 1" in result

    def test_render_complex_template(self):
        template = textwrap.dedent("""\
            {% if phase == "pilot" %}Run pilot.{% else %}Run confirm.{% endif %}
            {% for item in items %}
            - {{ item }}
            {% endfor %}
        """)
        wf = self._make_workflow(template)
        result = render_prompt(wf, {"phase": "pilot", "items": ["a", "b", "c"]})
        assert "Run pilot." in result
        assert "- a" in result
        assert "- b" in result
        assert "- c" in result


class TestWorkflowTemplatePhaseGuidance:
    """Tests that WORKFLOW.md.j2 preserves phase_type guidance for runtime rendering."""

    TEMPLATE_PATH = Path(__file__).parent.parent / "scaffold" / "templates" / "WORKFLOW.md.j2"

    def _render_init_stage(self, context: dict) -> str:
        """Stage 1: Render the .j2 template as init_experiment would."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_PATH.parent)),
            keep_trailing_newline=True,
        )
        template = env.get_template(self.TEMPLATE_PATH.name)
        return template.render(**context)

    def _render_runtime_stage(self, init_output: str, context: dict) -> str:
        """Stage 2: Render the init output as the orchestrator would at runtime."""
        from jinja2 import BaseLoader
        from scaffold.workflow import _SilentUndefined

        env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        template = env.from_string(init_output)
        return template.render(**context)

    def test_template_preserves_phase_type_block(self):
        """After init rendering, the WORKFLOW.md contains literal {% if phase_type %} for runtime."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        assert "{% if phase_type %}" in init_output
        assert "Confirmatory phase" in init_output

    def test_confirm_phase_type_renders_at_runtime(self):
        """Two-stage rendering: phase_type='confirm' produces Confirmatory guidance."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)

        runtime_context = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
            "phase_type": "confirm",
        }
        final_output = self._render_runtime_stage(init_output, runtime_context)
        assert "Confirmatory phase" in final_output
        assert "pre-registered plan" in final_output

    def test_pilot_phase_type_renders_at_runtime(self):
        """Two-stage rendering: phase_type='pilot' produces Pilot guidance."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)

        runtime_context = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
            "phase_type": "pilot",
        }
        final_output = self._render_runtime_stage(init_output, runtime_context)
        assert "Pilot phase" in final_output
        assert "exploratory, not evidential" in final_output

    def test_no_phase_type_omits_guidance(self):
        """Two-stage rendering: phase_type=None produces no Phase Guidance section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)

        runtime_context = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
        }
        final_output = self._render_runtime_stage(init_output, runtime_context)
        assert "Phase Guidance" not in final_output


class TestWorkflowTemplateConfoundChecklist:
    """Tests that WORKFLOW.md.j2 renders the confound checklist for pilot/confirm phases only."""

    TEMPLATE_PATH = Path(__file__).parent.parent / "scaffold" / "templates" / "WORKFLOW.md.j2"

    def _render_init_stage(self, context: dict) -> str:
        """Stage 1: Render the .j2 template as init_experiment would."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_PATH.parent)),
            keep_trailing_newline=True,
        )
        template = env.get_template(self.TEMPLATE_PATH.name)
        return template.render(**context)

    def _render_runtime_stage(self, init_output: str, context: dict) -> str:
        """Stage 2: Render the init output as the orchestrator would at runtime."""
        from jinja2 import BaseLoader
        from scaffold.workflow import _SilentUndefined

        env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        template = env.from_string(init_output)
        return template.render(**context)

    def _make_runtime_context(self, **overrides) -> dict:
        """Build a standard runtime context with optional overrides."""
        ctx = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
        }
        ctx.update(overrides)
        return ctx

    def test_confound_checklist_renders_for_pilot(self):
        """Two-stage rendering: phase_type='pilot' produces the Confound Checklist section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(phase_type="pilot")
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Confound Checklist" in final_output
        assert "Data leakage" in final_output

    def test_confound_checklist_renders_for_confirm(self):
        """Two-stage rendering: phase_type='confirm' produces the Confound Checklist section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(phase_type="confirm")
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Confound Checklist" in final_output
        assert "Data leakage" in final_output

    def test_confound_checklist_absent_for_writeup(self):
        """Two-stage rendering: phase_type='writeup' does NOT produce the Confound Checklist."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(phase_type="writeup")
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Confound Checklist" not in final_output

    def test_confound_checklist_absent_when_no_phase_type(self):
        """Two-stage rendering: no phase_type produces no Confound Checklist."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context()  # no phase_type key
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Confound Checklist" not in final_output


class TestWorkflowTemplateRandomSeed:
    """Tests that WORKFLOW.md.j2 renders the reproducibility seed section conditionally."""

    TEMPLATE_PATH = Path(__file__).parent.parent / "scaffold" / "templates" / "WORKFLOW.md.j2"

    def _render_init_stage(self, context: dict) -> str:
        """Stage 1: Render the .j2 template as init_experiment would."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_PATH.parent)),
            keep_trailing_newline=True,
        )
        template = env.get_template(self.TEMPLATE_PATH.name)
        return template.render(**context)

    def _render_runtime_stage(self, init_output: str, context: dict) -> str:
        """Stage 2: Render the init output as the orchestrator would at runtime."""
        from jinja2 import BaseLoader
        from scaffold.workflow import _SilentUndefined

        env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        template = env.from_string(init_output)
        return template.render(**context)

    def _make_runtime_context(self, **overrides) -> dict:
        """Build a standard runtime context with optional overrides."""
        ctx = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
        }
        ctx.update(overrides)
        return ctx

    def test_seed_instruction_renders_when_set(self):
        """Two-stage rendering: random_seed=42 produces the Reproducibility section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(random_seed=42)
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Reproducibility" in final_output
        assert "random seed **42**" in final_output
        assert "metrics.random_seed_used" in final_output

    def test_seed_instruction_absent_when_none(self):
        """Two-stage rendering: random_seed=None omits the Reproducibility section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(random_seed=None)
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Reproducibility" not in final_output

    def test_seed_instruction_absent_when_not_set(self):
        """Two-stage rendering: no random_seed key omits the Reproducibility section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context()  # no random_seed key
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Reproducibility" not in final_output


class TestWorkflowTemplateEli5:
    """Tests that WORKFLOW.md.j2 includes eli5 field in the result.json example."""

    TEMPLATE_PATH = Path(__file__).parent.parent / "scaffold" / "templates" / "WORKFLOW.md.j2"

    def _render_init_stage(self, context: dict) -> str:
        """Stage 1: Render the .j2 template as init_experiment would."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_PATH.parent)),
            keep_trailing_newline=True,
        )
        template = env.get_template(self.TEMPLATE_PATH.name)
        return template.render(**context)

    def test_rendered_workflow_contains_eli5_in_result_json(self):
        """The rendered WORKFLOW.md contains 'eli5' in the result.json example block."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        assert '"eli5"' in init_output

    def test_rendered_workflow_contains_eli5_instruction(self):
        """The rendered WORKFLOW.md contains instructions about the eli5 field."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        assert "eli5" in init_output.lower()
        assert "required" in init_output.lower() or "plain language" in init_output.lower()

    def test_rendered_workflow_contains_thoughts_in_result_json(self):
        """The rendered WORKFLOW.md contains 'thoughts' in the result.json example block."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        assert '"thoughts"' in init_output


class TestWorkflowTemplateLiteratureSweep:
    """Tests that WORKFLOW.md.j2 renders the deep literature sweep section for first iteration."""

    TEMPLATE_PATH = Path(__file__).parent.parent / "scaffold" / "templates" / "WORKFLOW.md.j2"

    def _render_init_stage(self, context: dict) -> str:
        """Stage 1: Render the .j2 template as init_experiment would."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_PATH.parent)),
            keep_trailing_newline=True,
        )
        template = env.get_template(self.TEMPLATE_PATH.name)
        return template.render(**context)

    def _render_runtime_stage(self, init_output: str, context: dict) -> str:
        """Stage 2: Render the init output as the orchestrator would at runtime."""
        from jinja2 import BaseLoader
        from scaffold.workflow import _SilentUndefined

        env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        template = env.from_string(init_output)
        return template.render(**context)

    def _make_runtime_context(self, **overrides) -> dict:
        """Build a standard runtime context with optional overrides."""
        ctx = {
            "phase": "phase1",
            "lane": "oracle",
            "task": "run experiment",
            "gates_display": "No gates",
            "iteration": 1,
            "max_iterations": 5,
            "previous_failures": "",
        }
        ctx.update(overrides)
        return ctx

    def test_literature_sweep_renders_on_first_iteration_no_completed(self):
        """iteration=1 with no completed_phases renders the full literature sweep section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(iteration=1)
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Literature Review (Required Before Experiments)" in final_output
        assert "at least 10" in final_output

    def test_literature_sweep_absent_on_later_iterations(self):
        """iteration=2 does NOT render the literature sweep section."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(iteration=2)
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Literature Review (Required Before Experiments)" not in final_output

    def test_literature_sweep_absent_when_completed_phases_present(self):
        """iteration=1 with completed_phases present does NOT render the literature sweep."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(
            iteration=1,
            completed_phases=[{"phase_name": "phase0", "metrics": {}, "iterations": 1}],
        )
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "Literature Review (Required Before Experiments)" not in final_output

    def test_pilot_phase_mentions_literature_review(self):
        """Pilot phase guidance references LITERATURE_REVIEW.md."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(phase_type="pilot")
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "LITERATURE_REVIEW.md" in final_output

    def test_confirm_phase_mentions_literature_review(self):
        """Confirm phase guidance references LITERATURE_REVIEW.md."""
        init_context = {
            "experiment_name": "test-exp",
            "runtime": {"python_env": ".venv", "accelerator": "mps", "fallback": "cpu"},
        }
        init_output = self._render_init_stage(init_context)
        runtime_context = self._make_runtime_context(phase_type="confirm")
        final_output = self._render_runtime_stage(init_output, runtime_context)

        assert "LITERATURE_REVIEW.md" in final_output
