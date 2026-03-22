# Scaffold Gaps

Gaps discovered during end-to-end stress test on `~/test-experiment/` (2026-03-22).
Each gap has a severity, status, and description of what's needed to close it.

## Fixed in This Pass

### G1: `launch` command stops after init (P0) -- FIXED
**File:** `scaffold/cli.py`
**Was:** `launch` called `init_experiment()` and stopped. Never chained to `scaffold run --auto`.
**Fix:** After init, creates Orchestrator with ClaudeCodeBackend and calls `run_all(auto=True)`.

### G2: Linear not wired into orchestrator or init (P0) -- FIXED
**File:** `scaffold/init.py`, `scaffold/orchestrator.py`
**Was:** LinearClient existed as standalone module, never called during init or phase execution.
**Fix:** Init creates Linear issue and saves ID to `.scaffold/linear.json`. Orchestrator loads it, updates status to "In Progress", posts gate reports as comments, updates to "Done" on completion. Graceful degradation on Linear errors.

### G3: Source docs not copied during launch (P1) -- FIXED
**File:** `scaffold/cli.py`
**Was:** `launch` never copied original research documents to `background-work/source-docs/`.
**Fix:** After init, copies each `result.source_documents` file to experiment dir.

### G4: WORKFLOW.md hooks not passed to runner (P1) -- FIXED
**File:** `scaffold/orchestrator.py`
**Was:** Orchestrator loaded WORKFLOW.md hooks but never passed them to `runner.execute()`.
**Fix:** Passes `workflow.hooks` as the `hooks` parameter to runner.

### G5/G9: Hook key name mismatch (P1) -- FIXED
**File:** `scaffold/runner.py`
**Was:** WORKFLOW.md could use `before_run`/`after_run` but runner only checked `pre_run`/`post_run`.
**Fix:** `AgentRunner.execute()` normalizes hook keys, accepting both naming conventions.

### G6: init_experiment doesn't run git init (P2) -- FIXED
**File:** `scaffold/init.py`
**Was:** `skip_external` was a no-op -- no external commands were ever run.
**Fix:** When `skip_external=False`, runs `git init` + initial commit. Graceful degradation if git unavailable.

### G8: ClaudeCodeBackend doesn't parse result.json (P1) -- FIXED
**File:** `scaffold/runner.py`
**Was:** ClaudeCodeBackend only captured stdout/stderr, ignoring agent-produced result.json.
**Fix:** After subprocess completes, reads `cwd/result.json` and populates metrics/artifacts in RunResult.

### G24: All-SKIP gates falsely pass (P0) -- FIXED
**File:** `scaffold/gates.py`
**Was:** `evaluate_phase_gates()` returned `overall_pass=True` when ALL gates evaluated as SKIP (no metrics found). This meant phases advanced with zero experimental work done -- the agent could produce nothing and the phase would "pass."
**Fix:** Added check: if all gates are SKIP (no PASS or FAIL results), `overall_pass = False`. Mixed PASS+SKIP still passes (some lanes may report metrics from different runs).

### G25: ClaudeCodeBackend has no tool access (P0) -- FIXED
**File:** `scaffold/runner.py`
**Was:** `claude --print` runs in non-interactive mode where tool use requires user permission. Since there's no user, the agent could not use Read, Write, Bash, or any other tools. The agent produced only text output, never modifying files or running experiments.
**Fix:** Added `--dangerously-skip-permissions` flag so the agent has full tool access within the experiment directory.

### G27: Orchestrator ignores RunResult.metrics and experiment-root result.json (P0) -- FIXED
**File:** `scaffold/orchestrator.py`
**Was:** `_collect_metrics()` only searched `results/` subdirectories for `result.json` files. The agent writes `result.json` in the experiment root, and ClaudeCodeBackend captures it into `RunResult.metrics`, but the orchestrator used neither. Gates always evaluated as all-SKIP on the first iteration.
**Fix:** `_collect_metrics()` now searches three sources: (1) `results/` subdirectories, (2) experiment root `result.json`, (3) `RunResult.metrics` from the runner. Later sources override earlier ones.

### G26: WORKFLOW.md prompt missing gate metrics and result.json convention (P0) -- FIXED
**File:** `scaffold/templates/WORKFLOW.md.j2`, `scaffold/orchestrator.py`
**Was:** The WORKFLOW.md prompt template told the agent to "check PREREG.md for gates" but never explicitly listed the gate metrics or told the agent about the result.json convention. The agent had no idea what metrics to produce or how to report them.
**Fix:** Added `{{ gates_display }}` to the template with per-gate metric/threshold/comparator display. Added result.json convention section with format instructions. Added `{{ iteration }}` and `{{ max_iterations }}` for iteration context. Orchestrator now builds `gates_display` from phase config and passes it in the render context.

---

## Open Gaps (Not Fixed Yet)

### G10: Beads (bd) integration not wired
**Severity:** P2
**File:** `scaffold/tracker.py`
**Status:** Module exists with full API (init_beads, create_lane_issues, create_phase_milestones, close_phase, sync, get_ready_work) but is NEVER called from init, orchestrator, or CLI.
**What's needed:**
- `init_experiment()` should call `init_beads()`, `create_lane_issues()`, `create_phase_milestones()` when `skip_external=False`
- Orchestrator should call `update_phase_status()` on phase start and `close_phase()` on phase complete
- Landing-the-plane should call `sync()`
- Requires `bd` CLI to be installed on the machine
**Workaround:** Agents can manually run `bd` commands since AGENTS.md documents the CLI

### G11: Venv creation not implemented
**Severity:** P2
**File:** `scaffold/init.py`
**Status:** The plan says init should create `.venv` but this is not implemented.
**What's needed:** `python -m venv .venv` + `pip install -e .` (or at least venv creation)
**Workaround:** Users can create venv manually after init

### G12: Writing phase has no specialized prompt
**Severity:** P1
**File:** N/A (missing feature)
**Status:** The orchestrator dispatches the same WORKFLOW.md prompt for all phases. There's no mechanism to tell the agent to produce `paper/distill/index.html` and `paper/main.tex` during the writing phase.
**What's needed:**
- Phase-specific prompt templates or prompt sections in WORKFLOW.md that activate for the writing phase
- Instructions for the agent to use `generate_distill_html()` from publisher.py
- Instructions to write LaTeX manuscript and compile with `compile_latex()`
**Workaround:** Manually instruct the agent to write papers

### G13: Publisher not auto-invoked after writing phase
**Severity:** P2
**File:** `scaffold/orchestrator.py`, `scaffold/cli.py`
**Status:** After writing phase gates pass, the orchestrator should call `scaffold publish` automatically. Currently it just marks the phase as COMPLETED.
**What's needed:** Orchestrator checks if the completed phase is the last one (or a "writing" phase), then invokes the publisher
**Workaround:** Run `scaffold publish` manually

### G14: Negative result detection not implemented
**Severity:** P2
**File:** `scaffold/orchestrator.py`
**Status:** State machine supports NEGATIVE_RESULT transitions, but the orchestrator never transitions to NEGATIVE_RESULT. It always returns GATE_FAILED after max iterations.
**What's needed:**
- Heuristic or agent signal for when results clearly contradict the hypothesis (vs just failing to meet thresholds)
- Could be a special key in result.json: `"negative_result": true`
- Orchestrator should detect this and transition to NEGATIVE_RESULT instead of GATE_FAILED
**Workaround:** Manual status update via `scaffold approve` after analysis

### G15: Agent gets no feedback between iterations
**Severity:** P1
**File:** `scaffold/orchestrator.py`
**Status:** When gates fail and the orchestrator retries, the agent gets the exact same rendered prompt with no context about what happened in previous iterations or why gates failed.
**What's needed:**
- Append gate failure details to the prompt for the next iteration
- Include which metrics were missing or below threshold
- Include iteration count ("this is iteration 3 of max 20")
- Ideally include a summary of what the previous iteration produced
**Workaround:** The agent can read CURRENT_STATE.md and result.json files to get context, but only if the previous iteration wrote them

### G16: DOCX support not implemented
**Severity:** P3
**File:** `scaffold/intake.py:209-210`
**Status:** Returns placeholder string: `"[DOCX file: {name} - docx support not yet implemented]"`
**What's needed:** python-docx or similar library for text extraction
**Workaround:** Convert DOCX to markdown before running intake

### G17: Interactive init mode not implemented
**Severity:** P3
**File:** `scaffold/cli.py:35-36`
**Status:** CLI prints error and exits if `--config` not provided: `"Error: --config is required (interactive mode not yet implemented)"`
**What's needed:** Interactive prompts for experiment name, research question, etc. (as specified in the original plan Step 4)
**Workaround:** Always use `--config` or `scaffold launch`

### G18: Observability not wired into orchestrator gate reports
**Severity:** P2
**File:** `scaffold/orchestrator.py`
**Status:** Orchestrator logs basic events (phase_started, gate_evaluated, gate_failed, phase_completed) but doesn't log:
- Full gate report details (which metrics, observed values)
- Run duration
- Iteration-level summaries
**What's needed:** Richer structured logging with gate report details and timing

### G19: Artifact registration not wired into orchestrator
**Severity:** P2
**File:** `scaffold/orchestrator.py`
**Status:** Orchestrator has an `ArtifactRegistry` (`self.artifacts`) but never registers artifacts from RunResult.artifacts or result.json. RESULTS_INDEX.md is never updated programmatically.
**What's needed:** After each run, register artifacts from RunResult into the ArtifactRegistry and re-render RESULTS_INDEX.md
**Workaround:** Agents update RESULTS_INDEX.md manually (as AGENTS.md instructs)

### G20: Phase dependencies not enforced
**Severity:** P2
**File:** `scaffold/orchestrator.py`
**Status:** PhaseConfig has `depends_on` field but `run_all()` doesn't check dependencies. It just runs phases in order and relies on sequential execution.
**What's needed:** Before running a phase, check that all `depends_on` phases are COMPLETED
**Workaround:** Phases are run sequentially so dependencies are implicitly satisfied if they're ordered correctly in config

### G21: Config doesn't persist reproducibility section
**Severity:** P3
**File:** `scaffold/config.py`
**Status:** The `ExperimentConfig` dataclass has a `reproducibility` field but it's always empty dict by default. The template renders it, but intake doesn't synthesize it.
**What's needed:** Add reproducibility fields to intake synthesis prompt (git hash, seed, etc.)
**Workaround:** Manually add to experiment.yaml after init

### G22: No experiment resumption after interruption
**Severity:** P1
**File:** `scaffold/orchestrator.py`, `scaffold/cli.py`
**Status:** If the orchestrator is interrupted mid-phase (e.g., process killed), state is persisted but there's no explicit resume mechanism. Running `scaffold run` again starts from the current phase state, which should work for NOT_STARTED and GATE_FAILED phases, but IN_PROGRESS phases would need special handling.
**What's needed:**
- `scaffold run` should detect IN_PROGRESS phases and resume them
- Currently transitions from IN_PROGRESS directly to IN_PROGRESS would fail (only GATE_CHECK is valid from IN_PROGRESS)
- Need to handle interrupted state recovery
**Workaround:** Manually advance state via direct JSON editing

### G28: Stale result.json not cleaned between phases
**Severity:** P2
**File:** `scaffold/orchestrator.py`
**Status:** When a phase passes gates and advances, the result.json files from that phase remain on disk. When the next phase starts, the orchestrator's `_collect_metrics()` finds the old metrics. With the G24 fix (all-SKIP = FAIL), this doesn't cause false positives because old phase metrics won't match new phase gate names. But it's messy and could confuse agents.
**What's needed:** At the start of each phase (before dispatching to the agent), clean up stale result.json files from previous phases.
**Workaround:** Manually delete result.json between phases (current approach).

### G29: Agent stalls after long-running experiment scripts (P0) -- FIXED
**File:** `scaffold/runner.py`, `scaffold/orchestrator.py`
**Was:** ClaudeCodeBackend had no timeout on subprocess.run(). When an agent stalled after a 112-minute experiment, the process hung indefinitely.
**Fix:** Added `default_timeout=14400` (4 hours) to ClaudeCodeBackend. When no explicit timeout is passed, the default is used. Orchestrator also passes its own `default_timeout` to the runner. 8 new tests.

### G30: Retry iterations have no inter-iteration feedback (P0) -- FIXED
**File:** `scaffold/orchestrator.py`, `scaffold/templates/WORKFLOW.md.j2`
**Was:** When gates failed, the orchestrator retried with the exact same prompt. The agent had no context about why previous iterations failed, what metrics were observed, or what thresholds were missed.
**Fix:** After gate failure, the orchestrator now builds a `previous_failures` string containing each failed/skipped metric, its observed value, and the required threshold. This is passed as a template variable and rendered in the WORKFLOW.md under a "Previous Gate Failures" section. The agent can now see exactly what went wrong and adapt. 2 new tests.

### G31: Orchestrator burns all iterations when agent cannot start (P0) -- FIXED
**File:** `scaffold/orchestrator.py`
**Was:** When the agent failed to start (e.g., "Credit balance is too low", CLI not found), the orchestrator treated each failed run the same as a successful run with missing metrics. It burned through all 20 iterations in ~40 seconds, each producing no result.json, each evaluating as all-SKIP. No distinction between "agent ran but produced no metrics" and "agent cannot start."
**Fix:** Added consecutive agent failure tracking. If the agent returns `success=False` with non-zero returncode for `max_consecutive_agent_failures` (3) iterations in a row, the orchestrator logs an `agent_error_abort` event and stops early. The counter resets when an agent run succeeds. 3 new tests.

### G32: ClaudeCodeBackend uses API key instead of OAuth (P0) -- FIXED
**File:** `scaffold/runner.py`
**Was:** ClaudeCodeBackend launched `claude --print` as a subprocess that inherited the parent process environment. When `ANTHROPIC_API_KEY` was set (e.g., for other tools), the CLI used API credits instead of the user's OAuth session. This caused "Credit balance is too low" failures even when the user was logged in with OAuth.
**Fix:** Before spawning the subprocess, ClaudeCodeBackend now checks for `ANTHROPIC_API_KEY` in the environment and strips it if present, so the CLI falls through to OAuth authentication. Other env vars are preserved. 3 new tests.

### G23: No budget/cost tracking
**Severity:** P3
**File:** `scaffold/config.py`, `scaffold/orchestrator.py`
**Status:** ExperimentConfig has a `budget` field (default 0.0) but nothing tracks actual costs. Claude CLI usage is not metered by the scaffold.
**What's needed:** Parse claude CLI output for token usage, track cumulative cost per phase
**Workaround:** Monitor costs externally
