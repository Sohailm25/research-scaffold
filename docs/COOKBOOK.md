# Cookbook

Common usage patterns for the research-scaffold harness.

## Create an experiment from a config file

```bash
scaffold init my-experiment --config path/to/experiment.yaml --root ~/experiments
```

This creates `~/experiments/my-experiment/` with all state files, templates, and directory structure.

## Run a single phase

```bash
scaffold run -e ~/experiments/my-experiment --phase "Phase 1" --backend script
```

The orchestrator runs the phase iteratively until gates pass or max iterations (default 20) are hit.

## Auto-advance through all phases

```bash
scaffold run -e ~/experiments/my-experiment --auto --backend script
```

Runs each phase in order. Stops at phases marked `requires_human_review` or on gate failure.

## Check gate status without running

```bash
scaffold gate-check -e ~/experiments/my-experiment --phase "Phase 1"
```

Reads existing `result.json` files and evaluates gates.

## Approve a human-review gate

```bash
scaffold approve -e ~/experiments/my-experiment --phase "Phase 1"
```

Advances a phase from HUMAN_REVIEW to COMPLETED.

## View experiment status

```bash
scaffold status -e ~/experiments/my-experiment
```

Shows all phases with their current status and iteration counts.

## Publish to website

```bash
scaffold publish -e ~/experiments/my-experiment \
  --website ~/Documents/Sohailm25.github.io \
  --title "My Experiment Title" \
  --description "One-line finding" \
  --outcome positive
```

Deploys Distill HTML and PDF to the website repo.

## Writing a result.json

Every agent run or script should write a `result.json` in the working directory:

```json
{
  "metrics": {
    "cross_entropy_delta_nats": 0.05,
    "p_value": 0.003,
    "cohens_d": 0.45
  },
  "artifacts": ["results/lane/figure.png"],
  "status": "success"
}
```

The orchestrator reads this for gate evaluation.

## Experiment config structure

```yaml
experiment:
  name: my-experiment
  thesis: "What we're testing"

research_question: "Does X cause Y?"

runtime:
  python_env: .venv
  accelerator: mps
  fallback: cpu

models:
  development:
    name: google/gemma-2-2b
    purpose: fast iteration
  primary:
    name: google/gemma-2-9b
    purpose: main results

hypotheses:
  primary: "X is associated with Y"
  secondary:
    - "The effect is stronger in condition A"

null_models:
  - name: random_baseline
    description: "Random assignment should show no effect"

framing_locks:
  - "This is observational, not causal"

required_lanes:
  - baseline
  - main_effect

phases:
  - name: "Phase 1"
    description: "Baseline measurements"
    gates:
      - metric: p_value
        threshold: 0.05
        comparator: lte
    requires_human_review: false

statistics:
  significance_level: 0.05
  effect_size_minimum: 0.2

reproducibility:
  seed_policy: fixed
  seeds: [42, 123, 456]
```

## Gate comparators

| Comparator | Meaning |
|-----------|---------|
| `gte` | observed >= threshold |
| `lte` | observed <= threshold |
| `gt` | observed > threshold |
| `lt` | observed < threshold |
| `eq` | observed == threshold |

## Directory structure after init

```
my-experiment/
  .scaffold/state.json        # Machine state
  .scaffold/artifacts.json    # Artifact registry
  configs/experiment.yaml     # Source of truth
  history/PREREG.md           # Preregistration (lock before running)
  AGENTS.md                   # Agent contract
  CURRENT_STATE.md            # Live state (read first every session)
  DECISIONS.md                # Non-obvious pivots
  SCRATCHPAD.md               # Execution checkpoints
  THOUGHT_LOG.md              # Research reflections
  WORKFLOW.md                 # Agent dispatch prompt
  results/RESULTS_INDEX.md    # Artifact registry (human-readable)
  results/infrastructure/     # Infrastructure artifacts
  results/{lane}/             # Per-lane results
  paper/                      # Manuscript
  figures/                    # Publication figures
```
