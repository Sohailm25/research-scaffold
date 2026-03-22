# research-scaffold

Autonomous research harness with epistemic guardrails. AI agents run experiment phases, check gates, and advance through the research lifecycle -- from document intake to published paper.

Built on patterns from [OpenAI Symphony](https://github.com/openai/symphony) (orchestrator/runner separation, WORKFLOW.md, workspace isolation) and battle-tested research process from [latent-depth-routing](https://github.com/Sohailm25/latent-depth-routing) (phase-gated execution, 8 epistemic standards, preregistration).

## How It Works

```
 Research docs          scaffold launch         Published paper
 (markdown, PDFs) ---> intake -> init -> run -> publish
                        |         |       |       |
                        claude    git     gates   Distill HTML
                        CLI       init   eval    + LaTeX PDF
                        (OAuth)   beads  loop    + GitHub Pages
                                  Linear
```

**Three-layer execution model:**

1. **Orchestrator** -- loads config, drives phase loops, evaluates gates mechanically (agent cannot self-game)
2. **Agent Runner** -- renders WORKFLOW.md prompt, dispatches to backend (script or claude CLI), runs lifecycle hooks
3. **Agent** -- operates within AGENTS.md contract, writes `result.json` with metrics, creates beads issues for follow-up

**Two-layer tracking:**

- **Linear** (outer) -- one issue per experiment on the [Experiments board](https://linear.app). Phase gate reports posted as comments.
- **Beads** (inner) -- git-native issue tracking within each experiment. Agents create/close issues during runs.

## Quick Start

### Install

```bash
git clone https://github.com/Sohailm25/research-scaffold.git
cd research-scaffold
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Initialize an experiment from config

```bash
scaffold init my-experiment --config path/to/experiment.yaml --root ~/experiments
```

This creates a standalone git repo at `~/experiments/my-experiment/` with:
- `AGENTS.md` -- agent contract with 8 epistemic standards
- `WORKFLOW.md` -- Symphony-style config+prompt for agent dispatch
- `configs/experiment.yaml` -- source of truth
- `history/PREREG.md` -- preregistration (locked before claim-bearing runs)
- `.scaffold/state.json` -- phase state machine
- `.beads/` -- git-native issue tracker
- Full directory structure for results, figures, paper, sessions, etc.

### Launch from research documents (end-to-end)

```bash
# Drop research docs into a directory
mkdir ~/ideas/my-experiment
cp paper.pdf notes.md IDEA.md ~/ideas/my-experiment/

# Launch -- intake -> init -> run
scaffold launch ~/ideas/my-experiment/ --root ~/experiments
```

The intake module reads all documents, synthesizes an experiment config via `claude` CLI (OAuth), and initializes the experiment. Add `--review-config` to pause for human review before proceeding. Add `--dry-run` to see the synthesized config without creating anything.

### Run experiment phases

```bash
# Run a single phase
scaffold run -e ~/experiments/my-experiment --phase "Phase 1"

# Auto-advance through all phases
scaffold run -e ~/experiments/my-experiment --auto

# Use claude CLI as the agent backend
scaffold run -e ~/experiments/my-experiment --backend claude --auto
```

Each phase runs iteratively: the agent executes, writes `result.json` with metrics, and the orchestrator evaluates gates. If gates fail, the phase retries (up to `--max-iterations`, default 20). If gates pass and the phase requires human review, execution pauses.

### Check status and approve gates

```bash
# View experiment status
scaffold status -e ~/experiments/my-experiment

# Evaluate gates without running
scaffold gate-check -e ~/experiments/my-experiment --phase "Phase 1"

# Human-approve a gate (advance from HUMAN_REVIEW to COMPLETED)
scaffold approve -e ~/experiments/my-experiment --phase "Phase 1"
```

### Publish to website

```bash
scaffold publish -e ~/experiments/my-experiment \
  --website ~/Documents/Sohailm25.github.io \
  --title "My Finding" \
  --description "One-line summary" \
  --outcome positive  # or mixed or negative
```

Generates a Distill-style HTML article (Everforest Dark theme) and deploys alongside a PDF to the website repo.

### List experiments from Linear

```bash
scaffold experiments
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed diagrams showing how all systems interact.

### System Topology

```
research-scaffold/     (this repo -- the harness tool)
  scaffold/            Python package
  tests/               381 tests
  guides/              Universal research process guides

~/experiments/         (generated experiment repos -- NOT in this repo)
  experiment-a/        Standalone git repo with .beads/, .scaffold/, AGENTS.md, etc.
  experiment-b/        Each experiment is independent
```

### Execution Flow

```
                     +------------------+
                     |   ORCHESTRATOR   |
                     |                  |
                     |  Phase loop:     |
                     |  run -> metrics  |
                     |  -> gate eval    |
                     |  -> retry/advance|
                     +--------+---------+
                              |
                     +--------v---------+
                     |   AGENT RUNNER   |
                     |                  |
                     |  hooks -> prompt |
                     |  -> dispatch     |
                     |  -> result.json  |
                     +--------+---------+
                              |
              +---------------+---------------+
              |                               |
     +--------v---------+           +--------v---------+
     |  ScriptBackend   |           | ClaudeCodeBackend|
     |  Python scripts  |           | claude --print   |
     +------------------+           +------------------+
```

### State Machine

```
Phase:  NOT_STARTED -> IN_PROGRESS -> GATE_CHECK -> GATE_PASSED -> COMPLETED
                                          |              |
                                     GATE_FAILED    HUMAN_REVIEW
                                     (retry loop)       |
                                          |          COMPLETED
                                    NEGATIVE_RESULT
                                          |
                                      COMPLETED
```

Negative results are valid publishable outcomes.

## Epistemic Standards

Every experiment inherits 8 epistemic standards from the AGENTS.md template:

1. **Assumption quarantine** -- label every claim as `known`, `observed`, `inferred`, or `unknown`
2. **Evidence-first reasoning** -- follow evidence, don't force conclusions
3. **No forced logic** -- if evidence doesn't support a claim, say so
4. **Claim-evidence proportionality** -- match language strength to evidence strength
5. **Adversarial self-questioning** -- answer 4 questions before claim-bearing runs:
   - What is the most likely design flaw?
   - What is the simplest confound that could explain a positive result?
   - What would failure look like, and is the run designed to detect it?
   - If the expected result appears immediately, what is the probability the implementation is wrong?
6. **Pre-register before running** -- hypotheses and gates locked before execution
7. **Skepticism toward clean results** -- suspiciously clean results trigger investigation
8. **Implementation skepticism** -- verify implementations independently

## Phase Gates

Gates are quantitative thresholds evaluated mechanically by the orchestrator:

```yaml
phases:
  - name: phase1_pilot
    description: "Pilot study"
    gates:
      - metric: p_value
        threshold: 0.05
        comparator: lte
      - metric: cohens_d
        threshold: 0.2
        comparator: gte
    requires_human_review: false
```

The agent writes metrics to `result.json`:

```json
{
  "metrics": {
    "p_value": 0.003,
    "cohens_d": 0.45
  },
  "artifacts": ["results/pilot/figure1.png"],
  "status": "success"
}
```

The orchestrator reads the metrics and evaluates gates. The agent never evaluates its own gates.

## Module Map

| Module | Purpose |
|--------|---------|
| `config.py` | ExperimentConfig schema + YAML loader |
| `gates.py` | Phase gate evaluation engine |
| `state.py` | Experiment/phase state machine + JSON persistence |
| `artifacts.py` | Artifact registry (JSON + Markdown dual persistence) |
| `init.py` | Experiment directory creation from Jinja2 templates |
| `intake.py` | Document intake via claude CLI (OAuth) |
| `orchestrator.py` | Iterative phase execution loop |
| `runner.py` | Agent backend protocol + implementations |
| `workflow.py` | WORKFLOW.md loader (YAML frontmatter + prompt) |
| `workspace.py` | Workspace manager + path safety |
| `hooks.py` | Lifecycle hook executor |
| `observability.py` | Structured JSONL session logging |
| `tracker.py` | Beads (bd) CLI adapter |
| `linear.py` | Linear GraphQL adapter |
| `publisher.py` | Publication pipeline (Distill HTML, LaTeX, website deploy) |
| `cli.py` | Click CLI entry point |

## Guides

Universal research process guides in `guides/`:

- `RESEARCH_PROCESS.md` -- end-to-end research lifecycle
- `EXPERIMENT_TEMPLATE.md` -- experiment design template
- `LATEX_STYLE_GUIDE.md` -- LaTeX manuscript formatting
- `DISTILL_STYLE_GUIDE.md` -- Distill web article formatting
- `FIGURE_CHART_STYLE_GUIDE.md` -- Figure styling (Everforest theme, matplotlib)

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# 381 tests covering all 16 modules
```

Tests use protocol-conforming test doubles (not mocks):
- `_FakeBackend` for agent runner
- `_FakeTransport` for Linear API
- `_FakeClaudeRunner` for intake LLM calls
- `_RecordingTracker` for beads commands
- `tmp_path` fixtures for all file operations

## Configuration

Global config at `~/.scaffold/config.yaml`:

```yaml
linear_api_key: lin_api_...
linear_project_slug: experiments-150cc04e8705
default_experiment_root: ~/experiments
```

## License

MIT
