# Architecture

## Overview

Research-scaffold is a three-layer autonomous research harness. It combines:

- **OpenAI Symphony patterns** (WORKFLOW.md config+prompt, workspace isolation, lifecycle hooks, orchestrator/runner separation)
- **Beads (bd)** for git-native issue tracking within each experiment
- **Linear** for experiment portfolio tracking across all experiments
- **Local file state** (.scaffold/state.json, artifacts.json) for experiment lifecycle

The harness itself is a Python package. Experiments are standalone git repos initialized by `scaffold init` into a configurable directory (default: `~/experiments/`).

---

## System Topology

```
+------------------------------------------------------------------+
|                        YOUR MACHINE                               |
|                                                                   |
|  ~/research-scaffold/          (this repo - the harness tool)     |
|  +--------------------------+                                     |
|  | scaffold/                |                                     |
|  |   cli.py                 |  <-- entry point                    |
|  |   intake.py              |  <-- reads docs, calls claude CLI   |
|  |   init.py                |  <-- creates experiment dirs        |
|  |   orchestrator.py        |  <-- drives phase loops             |
|  |   runner.py              |  <-- dispatches to agent backends   |
|  |   linear.py              |  <-- portfolio tracking             |
|  |   publisher.py           |  <-- website deployment             |
|  |   templates/*.j2         |  <-- Jinja2 experiment templates    |
|  +--------------------------+                                     |
|           |                                                       |
|           | scaffold init / scaffold launch                       |
|           v                                                       |
|  ~/experiments/                (generated experiment repos)        |
|  +---------------------------+  +---------------------------+     |
|  | experiment-a/             |  | experiment-b/             |     |
|  |   .git/                   |  |   .git/                   |     |
|  |   .beads/  (issue tracker)|  |   .beads/                 |     |
|  |   .scaffold/state.json    |  |   .scaffold/state.json    |     |
|  |   AGENTS.md               |  |   AGENTS.md               |     |
|  |   WORKFLOW.md             |  |   WORKFLOW.md             |     |
|  |   configs/experiment.yaml |  |   configs/experiment.yaml |     |
|  |   results/                |  |   results/                |     |
|  |   paper/                  |  |   paper/                  |     |
|  +---------------------------+  +---------------------------+     |
|                                                                   |
+------|------------------------------|-----------------------------+
       |                              |
       v                              v
  +----------+                  +----------+
  | Linear   |                  | GitHub   |
  | (API)    |                  | Pages    |
  |          |                  |          |
  | Exp.     |                  | Published|
  | portfolio|                  | articles |
  | board    |                  | (Distill)|
  +----------+                  +----------+
```

---

## Three-Layer Execution Model

Adapted from OpenAI Symphony's orchestrator/runner/agent separation:

```
 scaffold run --experiment ~/experiments/my-exp --auto
        |
        v
+--------------------------------------------------+
| LAYER 1: CLI (cli.py)                            |
|                                                  |
|  Parses args, creates Orchestrator, invokes      |
|  run_all() or run_phase()                        |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
| LAYER 2: ORCHESTRATOR (orchestrator.py)          |
|                                                  |
|  For each phase:                                 |
|    1. Check dependencies (depends_on)            |
|    2. Set state -> IN_PROGRESS                   |
|    3. Dispatch to AgentRunner                    |
|    4. Collect result.json metrics                |
|    5. Evaluate phase gates (gates.py)            |
|    6. If FAIL: retry (up to max_iterations)      |
|    7. If PASS + human_review: pause              |
|    8. If PASS: advance to next phase             |
|    9. Persist state after every transition        |
|                                                  |
|  KEY INVARIANT: Gate evaluation happens HERE,    |
|  never in the agent. Prevents self-gaming.       |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
| LAYER 3: AGENT RUNNER (runner.py)                |
|                                                  |
|  1. Run before_run hooks                         |
|  2. Render WORKFLOW.md prompt (workflow.py)       |
|  3. Dispatch to backend:                         |
|     - ScriptBackend: subprocess Python script    |
|     - ClaudeCodeBackend: claude --print          |
|  4. Parse result.json from working dir           |
|  5. Run after_run hooks                          |
|  6. Return RunResult                             |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
| AGENT (LLM or Script)                            |
|                                                  |
|  Operates within AGENTS.md contract:             |
|  - Reads CURRENT_STATE.md, SCRATCHPAD.md first   |
|  - Answers 4 adversarial questions before claims |
|  - Writes result.json with metrics               |
|  - Updates state files                           |
|  - Creates beads issues for follow-up work       |
+--------------------------------------------------+
```

---

## Two-Layer Tracking Architecture

```
+===============================================+
|           LINEAR (Outer Layer)                |
|           Experiment Portfolio                |
|                                               |
|  +--------+ +--------+ +--------+ +--------+ |
|  | Exp A  | | Exp B  | | Exp C  | | Exp D  | |
|  | Todo   | | Active | | Review | | Done   | |
|  +--------+ +--------+ +--------+ +--------+ |
|                  |                             |
|  One Linear issue = one experiment = one paper |
|  Phase gate reports posted as comments         |
+===============================================+
         |
         |  Each experiment internally uses:
         v
+===============================================+
|           BEADS (Inner Layer)                 |
|           Tasks Within One Experiment         |
|                                               |
|  .beads/issues.jsonl                          |
|                                               |
|  [x] Phase 0 milestone                       |
|  [x] oracle_alpha lane                       |
|  [ ] pattern_analysis lane                   |
|  [ ] Phase 1: run pilot                      |
|  [ ] Phase 2: confirmatory                   |
|                                               |
|  Agent creates/closes issues during runs      |
|  bd create / bd close / bd sync               |
+===============================================+

LINEAR sees the forest (all experiments).
BEADS sees the trees (tasks within one experiment).
```

### Integration Flow

```
scaffold init my-experiment
  |
  +--> Creates Linear issue "my-experiment" (status: Todo)
  +--> Creates experiment directory with bd init
  +--> Creates beads issues for each lane + phase milestone
  +--> Stores Linear issue ID in .scaffold/linear.json

scaffold run --experiment ~/experiments/my-experiment --auto
  |
  +--> Updates Linear issue to "In Progress"
  +--> For each phase:
  |      +--> Posts phase start comment to Linear
  |      +--> Runs iterative experiment loop
  |      |      Agent uses bd create/close for tasks
  |      +--> Posts gate report as Linear comment
  |      +--> If requires_human_review: pauses
  |
  +--> When writing phase done: Linear -> "In Review"

scaffold publish --experiment ~/experiments/my-experiment
  |
  +--> Deploys Distill HTML + PDF to website repo
  +--> Updates Linear issue to "Done"
```

---

## State Machine

### Phase States

```
                    NOT_STARTED
                        |
                        v
                    IN_PROGRESS <----+
                        |            |
                        v            |
                    GATE_CHECK       |
                   /    |    \       |
                  v     v     v      |
          GATE_PASSED  GATE_FAILED  NEGATIVE_RESULT
              |            |              |
              v            +--- retry ----+
         HUMAN_REVIEW                     |
              |                           v
              v                      COMPLETED
         COMPLETED
```

### Experiment States

```
PLANNING --> ACTIVE --> PAUSED --> WRITING --> COMPLETED
                                          \-> NEGATIVE_RESULT
```

Negative results are valid publishable outcomes. A failed hypothesis is still science.

---

## File System Layout

### Harness Repository (this repo)

```
research-scaffold/
  scaffold/              Python package (the tool)
    cli.py               Entry point: scaffold <command>
    config.py            ExperimentConfig schema + YAML loader
    gates.py             Phase gate evaluation engine
    state.py             State machine + JSON persistence
    artifacts.py         Artifact registry (JSON + Markdown)
    init.py              Experiment directory creation
    intake.py            Document intake via claude CLI
    orchestrator.py      Iterative phase execution loop
    runner.py            Agent backend protocol + implementations
    workflow.py          WORKFLOW.md loader (YAML frontmatter)
    workspace.py         Workspace manager + path safety
    hooks.py             Lifecycle hook executor
    observability.py     Structured JSONL logging
    tracker.py           Beads (bd) CLI adapter
    linear.py            Linear GraphQL adapter
    publisher.py         Publication pipeline
    templates/           13 Jinja2 templates for experiment init
  tests/                 381 tests
  guides/                Universal research process guides
  docs/                  Architecture + cookbook
```

### Generated Experiment Instance

```
~/experiments/my-experiment/
  .git/                           Standalone git repo
  .beads/                         Beads issue tracker (git-native)
  .scaffold/
    state.json                    Phase state machine
    artifacts.json                Artifact registry (machine-readable)
    linear.json                   Linear issue ID for this experiment
  AGENTS.md                       Agent contract (8 epistemic standards)
  WORKFLOW.md                     Symphony-style config+prompt for dispatch
  CURRENT_STATE.md                Live state (agents read first)
  DECISIONS.md                    Non-obvious pivots log
  SCRATCHPAD.md                   Execution checkpoints
  THOUGHT_LOG.md                  Research reflections
  configs/
    experiment.yaml               Source of truth
  history/
    PREREG.md                     Preregistration (locked before runs)
  results/
    RESULTS_INDEX.md              Artifact registry (human-readable)
    infrastructure/               Infrastructure artifacts
    <lane>/                       Per-lane results
  figures/                        Publication figures
  paper/
    main.tex                      LaTeX manuscript
    main.pdf                      Compiled PDF
    distill/                      Distill web article
      index.html
      figures/
  sessions/                       Session logs (JSONL)
  background-work/
    source-docs/                  Original intake documents
```

---

## Data Flow: End-to-End

```
 Research Documents (markdown, PDFs, notes)
        |
        | scaffold launch ~/ideas/my-experiment/
        v
 +------------------+
 | INTAKE           |  intake.py
 |                  |  Scans docs, sends to claude CLI (OAuth)
 |                  |  Synthesizes ExperimentConfig
 +------------------+
        |
        v
 +------------------+
 | INIT             |  init.py
 |                  |  Renders 13 Jinja2 templates
 |                  |  Creates directory structure
 |                  |  git init, beads init, Linear issue
 +------------------+
        |
        v
 +------------------+
 | ORCHESTRATOR     |  orchestrator.py
 |                  |
 |  Phase 0 -----+ |
 |  Phase 1 -----+ |  Each phase is an iterative loop:
 |  Phase 2 -----+ |  run -> collect metrics -> evaluate gates
 |  ...          |  |  -> retry or advance
 |  Writing -----+ |
 +------------------+
        |
        | For each iteration:
        v
 +------------------+
 | AGENT RUNNER     |  runner.py
 |  hooks -> prompt |
 |  -> dispatch     |
 |  -> result.json  |
 +------------------+
        |
        v
 +------------------+     +------------------+
 | GATE ENGINE      |     | ARTIFACT         |
 | gates.py         |     | REGISTRY         |
 |                  |     | artifacts.py     |
 | Evaluates phase  |     | Tracks outputs   |
 | gates against    |     | JSON + Markdown  |
 | result.json      |     |                  |
 +------------------+     +------------------+
        |
        v
 +------------------+
 | PUBLISHER        |  publisher.py
 |                  |
 |  Distill HTML    |  Everforest Dark theme
 |  LaTeX PDF       |  pdflatex pipeline
 |  Website deploy  |  GitHub Pages
 +------------------+
        |
        v
 +------------------+     +------------------+
 | LINEAR           |     | WEBSITE          |
 | linear.py        |     | publisher.py     |
 |                  |     |                  |
 | Issue -> Done    |     | /research/<name> |
 | Phase comments   |     | Distill article  |
 +------------------+     +------------------+
```

---

## Key Design Principles

### From OpenAI Symphony

| Pattern | How We Use It |
|---------|---------------|
| WORKFLOW.md | YAML frontmatter (runtime config) + Markdown body (agent prompt). Hot-reloadable per dispatch. |
| Orchestrator/Runner split | Orchestrator owns state + gates. Runner owns dispatch + hooks. Clean separation. |
| Workspace isolation | Each experiment is a standalone git repo. No shared mutable state between experiments. |
| Lifecycle hooks | before_run/after_run hooks in WORKFLOW.md frontmatter. HookRunner executes with timeout + fail-fast. |

### From Resattn (Battle-Tested Process)

| Pattern | How We Use It |
|---------|---------------|
| 8 Epistemic Standards | Baked into AGENTS.md.j2 template. Every experiment inherits them. |
| 4 Adversarial Questions | Required before claim-bearing runs. In AGENTS.md section 6. |
| Phase-gated execution | Quantitative gates in experiment.yaml. Mechanical evaluation by orchestrator. |
| Pre-run/post-run checkpoints | SCRATCHPAD.md format from resattn, verbatim in template. |
| Negative results as outcomes | NEGATIVE_RESULT state. Writing phase produces negative-results publication. |
| Claim-evidence proportionality | Framing locks, non-causal language, per-lane status tracking. |

### Novel to Research-Scaffold

| Pattern | Why |
|---------|-----|
| Document intake via LLM | Drop docs in a folder, get a full experiment config. Uses claude CLI (OAuth). |
| Two-layer tracking | Linear (portfolio) + Beads (per-experiment tasks). Neither alone is sufficient. |
| Iterative phase loops | Phases are not single-pass. Agent loops until gates met, negative result, or max iterations. |
| result.json convention | Universal metric contract. Any script or agent writes it. Gates read it. |
| Auto-publication pipeline | Distill HTML + LaTeX PDF + website deploy. From experiment to published page. |

---

## Module Dependency Graph

```
cli.py
  |
  +-- init.py -----------> config.py
  |     |                    |
  |     +-- templates/*.j2   +-- (YAML parsing)
  |     +-- state.py
  |     +-- tracker.py -----> beads CLI (bd)
  |
  +-- orchestrator.py
  |     |
  |     +-- config.py
  |     +-- state.py
  |     +-- gates.py
  |     +-- artifacts.py
  |     +-- runner.py
  |     |     |
  |     |     +-- hooks.py
  |     |     +-- workflow.py
  |     |     +-- (ScriptBackend | ClaudeCodeBackend)
  |     |
  |     +-- observability.py
  |     +-- workspace.py
  |
  +-- intake.py -----------> claude CLI (OAuth)
  |     |
  |     +-- config.py
  |
  +-- linear.py -----------> Linear GraphQL API
  |
  +-- publisher.py ---------> website repo (git)
        |
        +-- templates/distill.html.j2
```

---

## Security Model

- **No API keys in code.** Linear API key lives in `~/.scaffold/config.yaml`. LLM access via OAuth (claude CLI).
- **No secrets in experiments.** `.scaffold/` is gitignored. Linear issue IDs are non-sensitive.
- **Path traversal prevention.** `workspace.py` uses `Path.resolve()` containment checks.
- **Gate integrity.** Orchestrator evaluates gates, not the agent. Agent cannot self-report gate passage.
- **Beads is git-native.** Issue data lives in `.beads/` inside the repo. No external database.
