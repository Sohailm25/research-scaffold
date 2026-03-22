# [Experiment Name]

*Copy-paste this template for new experiments. Fill in every section before running anything.*

**Before starting:** Check if a prior experiment in the same domain has a `LESSONS_LEARNED.md` you should read. Domain-specific gotchas can save you hours of debugging and wasted compute.

**Date Created:** YYYY-MM-DD
**Status:** PLANNING | IN PROGRESS | COMPLETE
**Budget:** $XX allocated, $XX spent, $XX remaining

---

## Research Question

*What specific question are we trying to answer? Be precise.*

Example:
> Does activation steering effectiveness vary systematically with model size when holding architecture constant?

**Not this:** "Does steering work?"
**This:** "Does steering effectiveness (measured as coherent refusal rate on benign prompts) decrease, increase, or remain constant as we scale from 3B to 32B parameters within the Qwen 2.5 Instruct family?"

---

## Literature Context

*What exists? What's the gap? What papers are most relevant?*

### What's Known
- [Paper 1, Year] found that X using method Y on models Z
- [Paper 2, Year] showed that A but did not test B
- [Paper 3, Year] claims C generalizes, but only tested on D

### What's Unknown / Gap
- No one has tested X across [dimension we're varying]
- Existing work uses [method/dataset/model] but not [our approach]
- Prior work found Y but didn't investigate why

### Key Papers to Cite
1. [Author et al., Year] — [One sentence: what they found]
2. [Author et al., Year] — [One sentence: what they found]
3. [Author et al., Year] — [One sentence: what they found]

**Output:** Create `LITERATURE_REVIEW.md` with full summaries before writing the experiment plan.

---

## Hypothesis

*What do we expect to find? Why?*

**Hypothesis:** [Specific, testable prediction]

**Rationale:** [Why do we think this? What theory/observation suggests it?]

**Alternative hypotheses:**
1. [Hypothesis 2]
2. [Hypothesis 3]

**Distinguishing prediction:** [What observation would favor one hypothesis over another?]

---

## Methods

### Models

*List models with justification for each. Why these? Why not others?*

| Model | HF ID / Source | Params | Layers | Hidden Dim | Why This Model? |
|-------|---------------|--------|--------|-----------|----------------|
| [Name] | [org/model-id] | XB | N | D | [Control / Scaling / Architecture / etc.] |
| [Name] | [org/model-id] | XB | N | D | [Reason] |

**Architecture families:** [List them]
**Scale range:** [XB to YB]
**Instruction-tuned or base?** [Which and why?]

---

### Evaluation Protocol

*Define these ONCE. Never change mid-experiment.*

**Prompt count:** [N unique prompts, M repeats = N×M total]
**Decoding strategy:** [Greedy (temp=0) | Sampling (temp=X, top_p=Y)]
**Max generation tokens:** [N tokens, why this number?]

**Primary metric:** [Coherent refusal rate = # coherent refusals / total prompts]

**Secondary metrics:**
- [Metric 2: garbled output rate]
- [Metric 3: direction norm]
- [Metric 4: ...]

**Classification criteria:**

| Category | Definition | Example Output |
|----------|-----------|----------------|
| Coherent refusal | [Clear, grammatical refusal] | "I cannot assist with that request." |
| Garbled output | [Incoherent, repetitive, broken] | "R... R... refuse..." |
| Normal response | [Model answers helpfully] | "Here's how to bake a cake..." |

**Edge cases:**
- How do we classify [edge case 1]?
- How do we classify [edge case 2]?

**Success threshold:** [≥X% coherent refusal = works, <Y% = fails]

---

### Infrastructure

**Compute:**
- Cloud provider: [Modal | RunPod | AWS | GCP | etc.]
- GPU type: [A10G | A100-40GB | A100-80GB | H100]
- Selection logic: [≤XB params → GPU1, >XB params → GPU2]

**Libraries:**
- `transformers==X.Y.Z` (why this version?)
- `nnsight==X.Y.Z` (for activation extraction)
- `torch==X.Y.Z`
- [Other dependencies]

**Logging:**
- W&B project: `[project-name]`
- Result files: `results/[experiment-name]_YYYYMMDD_HHMMSS.json`
- Direction vectors: `directions/[model]_[method]_[layer].npy`

**Budget:** $XX total, allocated as:
- Phase 1: $XX
- Phase 2: $XX
- Phase 3: $XX
- Buffer (20%): $XX

**Hard stop:** $YY (do not exceed without approval)

---

## Experiment Plan

*Break into phases. Each phase has a gate (review + decision point).*

### Phase 1: [Pilot / Validation / Initial Sweep]

**Goal:** [What are we testing? What question does this answer?]

**Models:** [List]
**Conditions:** [List all combinations of variables]
**Expected runtime:** [X hours]
**Expected cost:** $XX

**Procedure:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Success criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]

**Decision point after Phase 1:**
- If [condition A], proceed to Phase 2 with [plan X]
- If [condition B], pivot to [plan Y]
- If [condition C], stop and report negative result

---

### Phase 2: [Main Sweeps / Scale Analysis / etc.]

**Goal:** [What are we testing? What question does this answer?]

**Models:** [List — depends on Phase 1 outcome]
**Conditions:** [List all combinations of variables]
**Expected runtime:** [X hours]
**Expected cost:** $XX

**Procedure:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Success criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]

**Decision point after Phase 2:**
- If [condition A], proceed to Phase 3
- If [condition B], skip Phase 3, proceed to analysis
- If [condition C], run additional experiments (budget permitting)

---

### Phase 3: [Edge Cases / Ablations / Quantization / etc.]

**Goal:** [What are we testing? What question does this answer?]

**Models:** [List]
**Conditions:** [List all combinations of variables]
**Expected runtime:** [X hours]
**Expected cost:** $XX

**Procedure:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Success criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]

---

## Control Test Protocol

*What known-good result validates the setup? Run this FIRST.*

**Model:** [Specific model + size]
**Configuration:** [Method, layer, multiplier, prompt count]
**Expected result:** [X% coherent refusal, Y% garbled, etc.]

**If control test fails:**
1. Check [possible failure mode 1]
2. Check [possible failure mode 2]
3. Re-run with verbose logging
4. Do NOT proceed to main experiments until control passes

**Control test checklist:**
- [ ] Model loads successfully
- [ ] Extraction produces direction with expected norm range [X-Y]
- [ ] Steering produces expected refusal rate (±Z%)
- [ ] Output quality matches expected (coherent, not garbled)
- [ ] Logs confirm correct layer, multiplier, prompt count

---

## Results

*Fill this in as experiments complete. Do not wait until the end.*

### Data Files

- `results/phase1_[experiment]_TIMESTAMP.json` — [Description]
- `results/phase2_[experiment]_TIMESTAMP.json` — [Description]
- `results/phase3_[experiment]_TIMESTAMP.json` — [Description]
- `results/FINAL_RESULTS.json` — [Consolidated, source of truth]

### Figures

- `figures/fig1_[description].pdf` + `.png` — [What it shows]
- `figures/fig2_[description].pdf` + `.png` — [What it shows]
- [Add as generated]

### Key Findings

*Update this section after each phase. One bullet per major finding.*

**Phase 1:**
- [Finding 1 with numbers]
- [Finding 2 with numbers]

**Phase 2:**
- [Finding 1 with numbers]
- [Finding 2 with numbers]

**Phase 3:**
- [Finding 1 with numbers]
- [Finding 2 with numbers]

**Anomalies / Negative Results:**
- [Unexpected result 1 — what we found, what we expected]
- [Unexpected result 2 — what we found, what we expected]

**Open questions:**
- [Question 1 — what would it take to answer this?]
- [Question 2 — what would it take to answer this?]

---

## Paper

*Plan the paper structure before running experiments. Revise as findings emerge.*

### Target Venue

**Primary:** [Conference/Journal Name, Deadline]
**Backup:** [Alternative Venue, Deadline]

**Why this venue?** [Audience, scope, acceptance rate, etc.]

### Draft Location

- **Main draft:** `paper/UNIFIED_DRAFT.md` (markdown for iteration)
- **LaTeX:** `arxiv/main.tex` (for submission)
- **Outline:** `paper/PAPER_OUTLINE.md` (structure + key claims per section)
- **Style guide:** `paper/STYLE_GUIDE.md` (voice, formatting, conventions)

### Paper Structure (Tentative)

1. Abstract (150-250 words)
2. Introduction
3. Background & Related Work
4. Methods
5. Results
   - 5.1 [Subsection 1]
   - 5.2 [Subsection 2]
6. Discussion
7. Limitations
8. Conclusion
9. Appendices

### Review Status

- [ ] **Outline complete** (structure + key claims per section)
- [ ] **Methods drafted** (reproducible detail)
- [ ] **Results drafted** (findings + figures)
- [ ] **Discussion drafted** (interpretation + mechanistic hypotheses)
- [ ] **Intro drafted** (framing + motivation)
- [ ] **Abstract drafted** (one paragraph distillation)
- [ ] **Pass 1: Self-review** (accuracy, citations, figure refs)
- [ ] **Pass 2: Deep critical review** (data consistency, overclaiming, contradictions)
- [ ] **Pass 3: Style guide pass** (kill AI slop, em dashes, forbidden words)
- [ ] **Pass 4: Final proofread** (read aloud, LaTeX compile, appendices)

### Key Claims (One Per Section)

*What does each section claim? Write this before drafting.*

- **§1 Intro:** [Claim]
- **§3 Background:** [Claim]
- **§4 Methods:** [Claim]
- **§5.1 Results:** [Claim]
- **§5.2 Results:** [Claim]
- **§6 Discussion:** [Claim]

---

## Execution Log

*Track progress. Update after each session.*

### YYYY-MM-DD — Phase 0: Planning

- [ ] Literature review complete (`LITERATURE_REVIEW.md`)
- [ ] Experiment plan drafted
- [ ] Shared library designed (`src/utils.py`, `src/extract.py`, etc.)
- [ ] Test suite written (at least 10 tests for core functions)
- [ ] Budget approved
- [ ] Control test protocol defined

**Notes:** [Any decisions, changes, insights]

---

### YYYY-MM-DD — Phase 1: [Name]

**Status:** COMPLETE | IN PROGRESS | BLOCKED

**Runs completed:**
- [Model 1, config A]: [result] — `results/[filename].json`
- [Model 2, config B]: [result] — `results/[filename].json`

**Anomalies:**
- [Anomaly 1]: [Description, hypothesis, next steps]

**Budget:** $XX spent, $YY remaining (Z% of total)

**Next:** [What's next? Review meeting? Phase 2? Pivot?]

**Notes:** [Anything worth remembering]

---

### YYYY-MM-DD — Phase 2: [Name]

**Status:** COMPLETE | IN PROGRESS | BLOCKED

**Runs completed:**
- [Model 1, config A]: [result] — `results/[filename].json`
- [Model 2, config B]: [result] — `results/[filename].json`

**Anomalies:**
- [Anomaly 1]: [Description, hypothesis, next steps]

**Budget:** $XX spent, $YY remaining (Z% of total)

**Next:** [What's next?]

**Notes:** [Anything worth remembering]

---

### YYYY-MM-DD — Phase 3: [Name]

**Status:** COMPLETE | IN PROGRESS | BLOCKED

**Runs completed:**
- [Model 1, config A]: [result] — `results/[filename].json`
- [Model 2, config B]: [result] — `results/[filename].json`

**Anomalies:**
- [Anomaly 1]: [Description, hypothesis, next steps]

**Budget:** $XX spent, $YY remaining (Z% of total)

**Next:** [Paper writing? Additional experiments?]

**Notes:** [Anything worth remembering]

---

### YYYY-MM-DD — Paper Writing

**Status:** DRAFTING | REVIEW | REVISION | COMPLETE

**Sections complete:**
- [X] Methods
- [X] Results
- [ ] Discussion
- [ ] Introduction
- [ ] Abstract

**Review passes:**
- [ ] Pass 1: Self-review (accuracy)
- [ ] Pass 2: Deep critical review (logic)
- [ ] Pass 3: Style guide pass (voice)
- [ ] Pass 4: Final proofread (polish)

**Figures:** [N/M complete]
**Tables:** [N/M complete]
**Appendices:** [N/M complete]

**Notes:** [Feedback from reviewers, changes made, etc.]

---

## Lessons Learned

*Fill this in AS YOU GO. Don't wait until the end. Domain-specific gotchas, tooling issues, things you'd do differently.*

**Note:** This section captures domain-specific lessons for this experiment. For universal process advice, see `RESEARCH_PROCESS.md` in the repo root.

### What Worked

*Specific techniques, tools, or approaches that worked well for this domain*

1. [Specific tool/approach] — [Why it worked, when to use it]
2. [Another technique] — [Details]

Examples:
- Control configuration that reliably validated setup
- Specific hyperparameters or settings that worked
- Tooling that was particularly effective

### What Didn't Work

*Failures, bugs, and surprises specific to this domain*

1. [Problem] — [What went wrong, why, how we fixed it or worked around it]
2. [Another issue] — [Details]

Examples:
- Architecture-specific failures (e.g., method X fails on model family Y)
- Parameter ranges that don't work (e.g., multiplier too low/high)
- Tooling incompatibilities or bugs

### Tooling Gotchas

*Technical issues specific to the tools/libraries/frameworks used*

- [Library X version Y issue] — [How to fix it]
- [Framework compatibility problem] — [Workaround]

Examples:
- Version incompatibilities
- Special handling required for certain model types
- Configuration issues

### Advice for Future Experiments in This Domain

*What you'd tell someone starting a similar experiment*

- [Specific actionable advice]
- [Another piece of advice]

Examples:
- "Start with [specific configuration] as your control test"
- "Model family X requires [specific adjustment]"
- "Tool Y works better than tool Z for [specific task]"

---

## Checklist: Before Calling It Done

**Experiments:**
- [ ] All phases complete
- [ ] Control tests passed
- [ ] Anomalies documented and investigated
- [ ] FINAL_RESULTS.json consolidated and validated
- [ ] Budget tracked and within limits

**Code:**
- [ ] Shared library tested (test suite passes)
- [ ] Scripts documented (docstrings + README)
- [ ] No hardcoded paths, API keys, or secrets
- [ ] Repo structure clean (no __pycache__, .DS_Store, etc.)

**Data:**
- [ ] All result files committed to git
- [ ] Direction vectors saved (.npy files)
- [ ] Logs saved (at least for key runs)
- [ ] Data audited against logs (spot-check 10 conditions)

**Paper:**
- [ ] All four review passes complete
- [ ] Figures at 300 DPI (PDF + PNG)
- [ ] Tables formatted consistently
- [ ] Appendices populated (no "[To be populated]" stubs)
- [ ] LaTeX compiles cleanly (pdflatex → bibtex → pdflatex → pdflatex)
- [ ] Bibliography complete (no "???" citations)

**Publication:**
- [ ] GitHub repo public with clean README
- [ ] Security scan passed (no API keys, tokens, personal paths)
- [ ] MIT license (or other open license)
- [ ] Website updated (research page + PDF + web version)
- [ ] arXiv submission ready (if applicable)

---

*Delete this line and everything above it when the template is filled in. Good luck!*
