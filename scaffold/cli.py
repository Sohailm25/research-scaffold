# ABOUTME: CLI entry point for the research-scaffold harness.
# ABOUTME: Provides subcommands for launch, init, run, status, gate-check, approve, publish, and experiments.

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def main():
    """Research scaffold: autonomous experiment harness."""
    pass


@main.command()
@click.argument("name")
@click.option("--root", type=click.Path(), default=".", help="Parent directory for experiment")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Path to experiment.yaml")
def init(name, root, config_path):
    """Initialize a new experiment directory.

    If --config is provided, uses that YAML file for configuration.
    Otherwise, creates a minimal experiment with the given NAME.
    """
    from scaffold.config import load_config
    from scaffold.init import init_experiment

    root = Path(root)
    if config_path:
        config = load_config(Path(config_path))
        experiment_dir = init_experiment(config, root, name=name, skip_external=False)
    else:
        click.echo("Error: --config is required (interactive mode not yet implemented)")
        raise SystemExit(1)

    click.echo(f"Experiment initialized at: {experiment_dir}")


@main.command()
@click.option(
    "--experiment", "-e", type=click.Path(exists=True), required=True,
    help="Experiment directory",
)
@click.option("--phase", "-p", help="Specific phase to run (default: current)")
@click.option(
    "--backend", "-b", type=click.Choice(["script", "claude"]), default="script",
    help="Agent backend",
)
@click.option("--auto/--no-auto", default=False, help="Auto-advance through phases")
@click.option("--max-iterations", type=int, default=20, help="Max iterations per phase")
def run(experiment, phase, backend, auto, max_iterations):
    """Run experiment phases."""
    from scaffold.orchestrator import Orchestrator
    from scaffold.runner import AgentRunner, ClaudeCodeBackend, ScriptBackend

    experiment_dir = Path(experiment)

    if backend == "script":
        agent_backend = ScriptBackend()
    else:
        agent_backend = ClaudeCodeBackend()

    runner = AgentRunner(backend=agent_backend)
    orchestrator = Orchestrator(experiment_dir, runner, max_iterations=max_iterations)

    if phase:
        result = orchestrator.run_phase(phase)
        _print_phase_result(result)
    else:
        results = orchestrator.run_all(auto=auto)
        for r in results:
            _print_phase_result(r)


@main.command()
@click.option(
    "--experiment", "-e", type=click.Path(exists=True), required=True,
    help="Experiment directory",
)
def status(experiment):
    """Show experiment status (phases, gates, artifacts)."""
    from scaffold.config import load_config
    from scaffold.state import ExperimentState

    experiment_dir = Path(experiment)
    state = ExperimentState.load(experiment_dir / ".scaffold" / "state.json")

    click.echo(f"Experiment: {state.experiment_name}")
    click.echo(f"Status: {state.status}")
    click.echo(f"Created: {state.created_at}")
    click.echo()
    click.echo("Phases:")
    for phase_state in state.phases:
        status_str = phase_state.status
        if phase_state.iteration_count > 0:
            status_str += f" (iteration {phase_state.iteration_count})"
        click.echo(f"  {phase_state.name}: {status_str}")


@main.command("gate-check")
@click.option(
    "--experiment", "-e", type=click.Path(exists=True), required=True,
    help="Experiment directory",
)
@click.option("--phase", "-p", required=True, help="Phase to check")
def gate_check(experiment, phase):
    """Evaluate gates for a phase without running."""
    from scaffold.gates import evaluate_phase_gates
    from scaffold.orchestrator import Orchestrator
    from scaffold.runner import AgentRunner, ScriptBackend

    experiment_dir = Path(experiment)
    runner = AgentRunner(backend=ScriptBackend())
    orchestrator = Orchestrator(experiment_dir, runner)
    metrics = orchestrator._collect_metrics(phase)

    # Find the phase config
    phase_config = None
    for p in orchestrator.config.phases:
        if p.name == phase:
            phase_config = p
            break

    if not phase_config:
        click.echo(f"Error: phase '{phase}' not found")
        raise SystemExit(1)

    report = evaluate_phase_gates(phase_config, metrics)
    click.echo(f"Phase: {phase}")
    click.echo(f"Overall: {'PASS' if report.overall_pass else 'FAIL'}")
    for result in report.results:
        click.echo(f"  {result.gate.metric}: {result.status} (observed={result.observed_value})")


@main.command()
@click.option(
    "--experiment", "-e", type=click.Path(exists=True), required=True,
    help="Experiment directory",
)
@click.option("--phase", "-p", required=True, help="Phase to approve")
def approve(experiment, phase):
    """Human-approve a phase gate (advance from HUMAN_REVIEW to COMPLETED)."""
    from scaffold.state import ExperimentState

    experiment_dir = Path(experiment)
    state = ExperimentState.load(experiment_dir / ".scaffold" / "state.json")

    phase_state = state._find_phase(phase)

    if phase_state.status != "HUMAN_REVIEW":
        click.echo(f"Error: phase '{phase}' is in status '{phase_state.status}', not HUMAN_REVIEW")
        raise SystemExit(1)

    state.advance_phase(phase, "COMPLETED")
    state.save(experiment_dir / ".scaffold" / "state.json")
    click.echo(f"Phase '{phase}' approved and advanced to COMPLETED")


@main.command("publish")
@click.option(
    "--experiment", "-e", type=click.Path(exists=True), required=True,
    help="Experiment directory",
)
@click.option("--website", "-w", type=click.Path(), help="Website repo path")
@click.option("--title", "-t", required=True, help="Article title")
@click.option("--description", "-d", required=True, help="One-line description")
@click.option(
    "--outcome", type=click.Choice(["positive", "mixed", "negative"]),
    default="positive",
)
def publish(experiment, website, title, description, outcome):
    """Publish experiment to website."""
    from scaffold.publisher import publish as do_publish

    experiment_dir = Path(experiment)
    website_path = Path(website) if website else Path.home() / ".scaffold" / "website-repo"

    result = do_publish(
        experiment_dir, website_path, title, description, abstract="", outcome=outcome
    )
    if result.success:
        click.echo(f"Published to: {result.article_dir}")
    else:
        click.echo(f"Publication failed: {result.message}")
        raise SystemExit(1)


@main.command()
@click.argument("docs_dir", type=click.Path(exists=True))
@click.option("--root", type=click.Path(), default=None, help="Parent directory for experiment")
@click.option("--review-config", is_flag=True, help="Pause to review synthesized config")
@click.option("--dry-run", is_flag=True, help="Print synthesized config without creating experiment")
def launch(docs_dir, root, review_config, dry_run):
    """Intake documents, synthesize config, initialize and run experiment."""
    from scaffold.intake import ClaudeCLIRunner, intake

    docs_path = Path(docs_dir)
    runner = ClaudeCLIRunner()

    click.echo(f"Scanning documents in {docs_path}...")
    result = intake(docs_path, runner)
    click.echo(f"Synthesized experiment: {result.experiment_name}")
    click.echo(f"Research question: {result.research_question}")
    click.echo(f"Lanes: {result.required_lanes}")
    click.echo(f"Phases: {[p['name'] for p in result.phases]}")

    if dry_run:
        import json
        click.echo("\n--- Synthesized Config ---")
        click.echo(json.dumps({
            "experiment_name": result.experiment_name,
            "research_question": result.research_question,
            "hypotheses": result.hypotheses,
            "null_models": result.null_models,
            "required_lanes": result.required_lanes,
            "phases": result.phases,
        }, indent=2))
        return

    if review_config:
        click.echo("\nReview the synthesized config above.")
        if not click.confirm("Proceed with initialization?"):
            click.echo("Aborted.")
            return

    config = result.to_experiment_config()
    experiment_root = Path(root) if root else Path.home() / "experiments"

    from scaffold.init import init_experiment
    experiment_dir = init_experiment(config, experiment_root, skip_external=False)
    click.echo(f"Experiment initialized at: {experiment_dir}")


@main.command()
def experiments():
    """List all experiments from the Linear project board."""
    from scaffold.linear import LinearClient

    client = LinearClient()
    issues = client.list_experiments()

    if not issues:
        click.echo("No experiments found.")
        return

    click.echo(f"{'Title':<40} {'State':<15} {'Updated':<12}")
    click.echo("-" * 67)
    for issue in issues:
        title = issue["title"][:38]
        state = issue.get("state", "?")
        updated = issue.get("updated_at", "")[:10]
        click.echo(f"{title:<40} {state:<15} {updated:<12}")


def _print_phase_result(result):
    """Print a PhaseResult to the terminal."""
    status = "PASS" if result.gate_passed else "FAIL"
    if result.negative_result:
        status = "NEGATIVE_RESULT"
    if result.requires_human_review:
        status = "AWAITING_REVIEW"
    click.echo(f"  {result.phase_name}: {status} ({result.iterations} iterations)")
