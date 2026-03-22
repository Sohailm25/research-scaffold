# ABOUTME: Tests for scaffold/workflow.py - WORKFLOW.md loader and prompt renderer.
# ABOUTME: Covers YAML frontmatter parsing, prompt body extraction, and Jinja2 rendering.

import textwrap

import pytest

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
