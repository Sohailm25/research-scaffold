# ABOUTME: Experiment directory initializer that renders templates and creates scaffold structure.
# ABOUTME: Creates a complete experiment workspace from an ExperimentConfig or YAML path.

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import jinja2

from scaffold.config import ExperimentConfig, load_config
from scaffold.state import ExperimentState


# Directories to create inside every experiment (relative to experiment root).
_DIRECTORIES = (
    "configs",
    "history",
    "sessions",
    "background-work",
    "background-work/source-docs",
    "background-work/papers",
    "scripts",
    "validation",
    "tests",
    "results",
    "results/infrastructure",
    "figures",
    "paper",
    "paper/figures",
    "paper/distill",
    "paper/distill/figures",
    "notebooks",
    "prompts",
    "research",
    "journal",
    "journal/logs",
    ".scaffold",
)

# Map from template file name to output path (relative to experiment root).
_TEMPLATE_MAP = {
    "gitignore.j2": ".gitignore",
    "README.md.j2": "README.md",
    "AGENTS.md.j2": "AGENTS.md",
    "WORKFLOW.md.j2": "WORKFLOW.md",
    "CURRENT_STATE.md.j2": "CURRENT_STATE.md",
    "DECISIONS.md.j2": "DECISIONS.md",
    "SCRATCHPAD.md.j2": "SCRATCHPAD.md",
    "THOUGHT_LOG.md.j2": "THOUGHT_LOG.md",
    "experiment.yaml.j2": "configs/experiment.yaml",
    "PREREG.md.j2": "history/PREREG.md",
    "SESSION_TEMPLATE.md.j2": "sessions/SESSION_TEMPLATE.md",
    "RESULTS_INDEX.md.j2": "results/RESULTS_INDEX.md",
}


def _build_template_context(config: ExperimentConfig, experiment_name: str) -> dict:
    """Build the Jinja2 template context dict from an ExperimentConfig."""
    # Convert nested dataclasses to plain dicts for template access
    models_dict = {
        "development": {"name": config.models.development.name, "purpose": config.models.development.purpose},
        "primary": {"name": config.models.primary.name, "purpose": config.models.primary.purpose},
    }
    if config.models.secondary is not None:
        models_dict["secondary"] = {
            "name": config.models.secondary.name,
            "purpose": config.models.secondary.purpose,
        }

    runtime_dict = {
        "python_env": config.runtime.python_env,
        "accelerator": config.runtime.accelerator,
        "fallback": config.runtime.fallback,
        "platform": config.runtime.platform,
    }

    phases_list = []
    for p in config.phases:
        gates_list = [
            {"metric": g.metric, "threshold": g.threshold, "comparator": g.comparator}
            for g in p.gates
        ]
        phases_list.append({
            "name": p.name,
            "description": p.description,
            "gates": gates_list,
            "requires_human_review": p.requires_human_review,
            "depends_on": p.depends_on,
        })

    hypotheses_dict = {
        "primary": config.hypotheses.primary,
        "secondary": config.hypotheses.secondary,
    }

    null_models_list = [
        {"name": nm.name, "description": nm.description}
        for nm in config.null_models
    ]

    return {
        "experiment_name": experiment_name,
        "research_question": config.research_question,
        "thesis": config.thesis,
        "framing_locks": config.framing_locks,
        "guardrails": config.guardrails,
        "required_lanes": config.required_lanes,
        "runtime": runtime_dict,
        "models": models_dict,
        "phases": phases_list,
        "hypotheses": hypotheses_dict,
        "null_models": null_models_list,
        "statistics": config.statistics,
        "reproducibility": config.reproducibility,
        "parent_overrides": [],
        "date": date.today().isoformat(),
    }


def _write_journal_current_state(exp_dir: Path, experiment_name: str) -> None:
    """Create journal/current_state.md directly (not from template)."""
    today = date.today().isoformat()
    content = f"""# Journal Current State

- Date: {today}
- Repo: standalone and initialized
- Branch: wip/{experiment_name}-scaffold
- Focus: Phase 0 - Experiment Design
- Experimental status: scaffold initialized, no runs executed yet
- Next action: complete literature review and Phase 0 planning
- Critical reminder: do not skip Phase 0 planning or jump to execution without cleared gates
"""
    (exp_dir / "journal" / "current_state.md").write_text(content)


def _write_references_md(exp_dir: Path) -> None:
    """Create background-work/REFERENCES.md directly (not from template)."""
    content = """# References

Track papers, tools, and external resources used in this experiment.

## Papers

| Paper | Year | Key Finding | Local Path |
|---|---|---|---|
| (none yet) | - | - | - |

## Tools and Libraries

| Tool | Version | Purpose |
|---|---|---|
| PyTorch | - | Model execution |
| Transformers | - | Model loading |

## URLs

- (none yet)
"""
    (exp_dir / "background-work" / "REFERENCES.md").write_text(content)


def init_experiment(
    config: ExperimentConfig | Path,
    root: Path,
    name: str | None = None,
    skip_external: bool = False,
    _linear_client: object | None = None,
) -> Path:
    """Initialize a complete experiment directory from config.

    Args:
        config: An ExperimentConfig object or a Path to an experiment YAML file.
        root: Parent directory where the experiment directory will be created.
        name: Override for the experiment directory name. Defaults to config.name.
        skip_external: If True, skip git init, beads init, and venv creation.
        _linear_client: Optional pre-configured LinearClient for testing.

    Returns:
        Path to the created experiment directory.

    Raises:
        FileExistsError: If the experiment directory already exists.
    """
    # Handle Path input: load config from YAML
    if isinstance(config, Path):
        config = load_config(config)

    experiment_name = name if name is not None else config.name
    exp_dir = root / experiment_name

    # Idempotency guard: refuse to overwrite
    if exp_dir.exists():
        raise FileExistsError(
            f"Experiment directory already exists: {exp_dir}"
        )

    # 1. Create directory structure
    exp_dir.mkdir(parents=True)
    for d in _DIRECTORIES:
        (exp_dir / d).mkdir(parents=True, exist_ok=True)

    # Create per-lane result directories
    for lane in config.required_lanes:
        (exp_dir / "results" / lane).mkdir(parents=True, exist_ok=True)

    # 2. Render Jinja2 templates
    templates_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
    )

    context = _build_template_context(config, experiment_name)

    for template_name, output_path in _TEMPLATE_MAP.items():
        template = env.get_template(template_name)
        rendered = template.render(context)
        (exp_dir / output_path).write_text(rendered)

    # 3. Create journal/current_state.md directly
    _write_journal_current_state(exp_dir, experiment_name)

    # 4. Create background-work/REFERENCES.md directly
    _write_references_md(exp_dir)

    # 5. Initialize .scaffold/state.json
    state = ExperimentState.from_config(config)
    state.save(exp_dir / ".scaffold" / "state.json")

    # 6. Initialize .scaffold/artifacts.json (JSON only; template already rendered RESULTS_INDEX.md)
    artifacts_path = exp_dir / ".scaffold" / "artifacts.json"
    artifacts_path.write_text(json.dumps([], indent=2) + "\n")

    # 7. Git init (when skip_external=False)
    if not skip_external:
        import subprocess

        try:
            subprocess.run(["git", "init"], cwd=exp_dir, capture_output=True, check=True)
            subprocess.run(["git", "add", "."], cwd=exp_dir, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initialize experiment via scaffold"],
                cwd=exp_dir,
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Git is optional

    # 8. Create Linear issue (graceful degradation)
    if not skip_external:
        try:
            linear = _linear_client
            if linear is None:
                from scaffold.linear import LinearClient
                linear = LinearClient()
            issue_id = linear.create_experiment_issue(
                title=experiment_name,
                description=config.research_question,
            )
            linear_json_path = exp_dir / ".scaffold" / "linear.json"
            linear_json_path.write_text(json.dumps({"issue_id": issue_id}) + "\n")
        except Exception:
            pass  # Linear is optional; continue without it

    return exp_dir
