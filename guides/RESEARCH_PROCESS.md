# Research Process Guide

*Universal process for research experiments, distilled from activation steering experiment (Feb 2026)*

This is the canonical process for all future experiments. It contains **universal process advice only** — no domain-specific lessons. For domain-specific gotchas (tooling issues, architecture quirks, publication details), see each experiment's `LESSONS_LEARNED.md`.

---

## Phase 0: Experiment Design

**Do this BEFORE running anything. No exceptions.**

### 0.1 Literature Review First

- [ ] **Read broadly, map the landscape** — What exists? What's the gap? What failed?
- [ ] **Find the closest prior work** — If someone did something similar, start there
- [ ] **Look for hidden negatives** — Papers rarely publish "we tried X and it didn't work"
- [ ] **Check recency** — In fast-moving fields, 6-month-old papers are outdated
- [ ] **Document claims you want to test** — "Paper X claims Y scales linearly; we'll test if..."

**Why:** A deep literature review prevents duplicating existing work and helps frame your unique contribution.

**Output:** `LITERATURE_REVIEW.md` with 3 sections: (1) What's known, (2) What's unknown, (3) What we'll test that's new

---

### 0.2 Write the Experiment Plan

**Structure it like V3_EXPERIMENT_PLAN.md:**

- [ ] **Executive Summary** — One paragraph: key discovery/hypothesis, how you'll test it, expected budget/timeline
- [ ] **Research Question** — Be specific. Not "does steering work" but "does steering effectiveness vary with model size holding architecture constant"
- [ ] **Phases with gates** — Phase 1 → review → decide → Phase 2. Never commit to everything upfront.
- [ ] **Budget breakdown** — Per phase, with hard stops. Track as you go.
- [ ] **Success criteria** — Quantitative thresholds. "≥60% coherent refusal = works, <20% = fails"
- [ ] **Control test protocol** — What known-good result validates your setup? Run this FIRST.
- [ ] **Decision points** — "If Phase 1 shows X, we proceed with Y. If not, pivot to Z."
- [ ] **Risk mitigation** — What breaks your plan? What's the fallback?

**Why:** Multiple revisions based on critical feedback catch flaws before you spend compute budget. Writing forces you to think through the whole experiment and expose confounding variables early.

---

### 0.3 Define Canonical Evaluation Protocol

Pick these ONCE, document them, and never change mid-experiment:

- [ ] **Sample size** — Pick one value and stick to it. Changing mid-experiment makes results incomparable.
- [ ] **Decoding strategy** — Greedy (deterministic) or sampling (stochastic). Each has trade-offs; pick based on what you're measuring.
- [ ] **Metrics** — Primary metric first. Define exactly what you're measuring.
- [ ] **Classification criteria** — Define categories with examples. Document edge cases.
- [ ] **Prompt set** — Lock the test set. If you need more data, create a separate validation set, don't mix.

**Why:** Changing evaluation protocol mid-stream makes every comparison table require asterisks and footnotes. Reviewers notice inconsistencies.

**Lesson:** Consistent arbitrary thresholds are better than case-by-case judgment. Pick success criteria upfront.

---

### 0.4 Control Test Protocol

**Always validate on a known-good configuration before running new experiments.**

Define your control test:
- [ ] Pick a configuration that should produce a known result
- [ ] Document the expected outcome with specific metrics
- [ ] If you don't match the expected result, your setup is broken. Don't proceed.

Run the control test:
1. After writing your core implementation
2. After any major infrastructure changes (dependencies, tooling, etc.)
3. When a new experiment fails mysteriously (control helps isolate whether it's setup vs experiment-specific)

**Why:** A control test validates your entire pipeline. It catches tooling issues, implementation bugs, and version incompatibilities before you burn budget on full experiments.

**Common use:** When implementing from a paper, verify your implementation matches the paper's reported results on their exact configuration before testing new hypotheses.

---

### 0.5 Infrastructure Planning

- [ ] **Shared library first** — Extract common functions into a shared module. Refactoring later wastes time; design it upfront.
- [ ] **Test suite before experiments** — Write tests for your utility functions before using them. Tests catch bugs before they corrupt your results.
- [ ] **Logging strategy** — Use dashboards for live tracking, structured files (JSON/CSV) as source of truth. Never trust dashboards alone.
- [ ] **Version control from day 1** — Git commit after every result. Label commits with phase and experiment name.
- [ ] **Data format** — Design your result file schema upfront. Changing schema later requires reformatting all existing data.

**Example schema structure:**
```json
{
  "experiment_id": "...",
  "phase": "...",
  "model": "...",
  "conditions": [
    {
      "param1": "...",
      "param2": "...",
      "metric": 0.90,
      "n_samples": 30,
      "samples": [...]
    }
  ]
}
```

**Key principle:** Include ALL metadata in every record (sample size, model, parameters, etc.). You'll grep for this later; make it easy to find.

---

## Phase 1: Infrastructure

### 1.1 Build the Shared Library

**Extract tested utility functions. Don't copy-paste between scripts.**

Identify functions used across multiple scripts:
- Data loading and preprocessing
- Metric computation
- Output classification/validation
- Model interaction (inference, layer access, etc.)
- Evaluation pipelines

**Why:** Duplicated functions drift over time. One script gets updated, another doesn't. Results become incomparable. Bugs hide in the divergence.

**Lesson:** If you copy-paste a function twice, it's time for a shared module. Extract it, test it, import it everywhere.

---

### 1.2 Write Tests BEFORE Experiments

**If you don't test your utilities, your experiments test them for you (badly).**

Write unit tests for core functions:
```python
def test_classification_function():
    assert classify("positive example") == "positive"
    assert classify("negative example") == "negative"
    assert classify("edge case") == expected_value

def test_metric_computation():
    assert compute_metric(known_input) == expected_output
    # Test edge cases (empty input, extreme values, etc.)

def test_data_preprocessing():
    result = preprocess(raw_data)
    assert result matches expected_format
```

**Why:** Testing after experiments means you discover bugs in the same run that generates your paper results. You can't tell which results are real and which are artifacts.

**Common bugs caught by tests:**
- False positives/negatives in classification
- Edge case handling (empty inputs, extreme values)
- Format incompatibilities across different data sources

---

### 1.3 Logging Strategy

**Two-tier system: Live dashboard for monitoring, structured files as source of truth.**

**Live tracking (W&B, TensorBoard, etc.):**
- Log all experimental parameters and metrics per run
- Tag runs by phase or experiment variant
- Use descriptive run names (not random IDs)
- Log sample outputs for manual inspection

**Structured files (JSON, CSV, etc.):**
- One result file per sweep: `phase_name_TIMESTAMP.json`
- Include EVERYTHING: all parameters, metrics, runtime metadata, sample outputs
- Never overwrite — append timestamp to filename
- Commit to git after every run

**Why:** Dashboards are great for quick checks but terrible for data provenance. Dashboards can cache stale data, fail to sync, or lose history. Always trust the file.

**Common mistake:** Logging some metrics only to dashboard, not to files. When writing the paper, you'll need every metric. If it's not in files, you'll have to re-run experiments.

---

## Phase 2: Execution

### 2.1 Run in Phases, Gate on Results

**Never launch everything at once. Run Phase 1 → review → decide → run Phase 2.**

Example gates:
- **After Phase 1 (pilot):** Review results. Decide which conditions proceed to full evaluation.
- **After Phase 2 (main sweep):** Review trends. Decide if expensive follow-ups are worth the cost.
- **After Phase 3 (ablations):** Review before paper writing. Decide if additional experiments are needed.

**Why:** Early phases often reveal failures or unexpected results. If you committed to all phases upfront, you'll waste budget on experiments that don't make sense given Phase 1 outcomes.

**Lesson:** A phase gate is not just a review meeting. It's a decision point with 3 outcomes: (1) proceed as planned, (2) pivot, (3) stop. Be ready for all three.

---

### 2.2 Track Budget Continuously

**Don't wait until you're out of money to check spending.**

Simple tracker format (update in `BUDGET.md` after every run):
```
Phase 1: $X / $Y (Z%)
  - Experiment A: $X.XX
  - Experiment B: $X.XX
  - Reruns/debugging: $X.XX
  - Buffer: $X.XX
```

Track after every run:
- Cost per experiment
- Cumulative spend per phase
- Percentage of total budget used
- Estimated remaining budget vs remaining work

**Why:** Mid-phase budget checks often reveal that later phases won't fit in remaining budget. Tracking early lets you cut low-priority experiments before burning all your budget.

**Lesson:** Cloud compute is metered. If you're not tracking, you're guessing. Always know your burn rate.

---

### 2.3 Control-Test New Scripts Before Sweeping

**Validate on the control configuration before launching expensive sweeps.**

Protocol:
1. Write new script
2. Run on your control configuration (from Phase 0)
3. Expected: matches known-good result
4. If pass → proceed to full sweep
5. If fail → debug, repeat

**Why:** Running a broken script on 50 configurations wastes budget. A 5-minute control test can prevent hours of wasted compute.

---

### 2.4 Document Anomalies Immediately

**Don't wait for paper writing to investigate weird results.**

When you see unexpected results:
1. Investigate immediately (test variations, check control, review logs)
2. Document in `FINDINGS_LOG.md` or `LESSONS_LEARNED.md` the same day
3. Form hypothesis about cause
4. Decide: is this a bug, an edge case, or a finding?

**Why:** If you wait until paper writing to investigate, you've lost the experiment context. You'll spend hours reconstructing what happened. Document while it's fresh.

**Format for anomaly documentation:**
```markdown
## YYYY-MM-DD — [Anomaly Title]

**Observation:** [What you saw that was unexpected]

**Tests run:**
- [Test 1: result]
- [Test 2: result]

**Hypothesis:** [Why might this be happening?]

**Next step:** [Report as finding / debug further / document limitation]
```

---

### 2.5 Keep Raw Data

**Structured files are source of truth. Dashboards lie, logs rotate, but files persist.**

Store everything:
- **Result files** — Full outputs, all metrics, all samples (structured JSON/CSV)
- **Intermediate artifacts** — Model outputs, computed representations, cached results
- **Examples** — At least 10 examples per condition, full outputs (not truncated)
- **Logs** — Console output from every run (for debugging failures)

**Why:** Deep review and paper writing surface questions you didn't anticipate. If you logged the data, you answer in minutes. If you didn't, you re-run experiments (time + money).

**Common mistake:** Not saving intermediate results. When a reviewer asks "what was the value of X?", you'll need to re-run if you didn't log it.

---

## Phase 3: Analysis & Consolidation

### 3.1 Consolidate Results into Structured Format

**Create a single source-of-truth file: FINAL_RESULTS.json**

Our schema:
```json
{
  "metadata": {
    "experiment": "activation-steering-cross-model",
    "date_range": "2026-02-12 to 2026-02-14",
    "total_cost": "$52.47",
    "models_tested": 7,
    "conditions_tested": 247
  },
  "phase1_architecture_comparison": { ... },
  "phase2_qwen_size_sweep": { ... },
  "phase2_gemma_size_sweep": { ... },
  "phase3_quantization": { ... },
  "gap_fills": { ... }
}
```

**Why:** We had 47 result files scattered across 3 directories. Creating FINAL_RESULTS.json meant:
- One file to check for any number
- One file to validate against logs
- One file to share with reviewers
- One file to archive

We spent 3 hours consolidating. Should have designed the schema upfront and merged incrementally.

---

### 3.2 Generate Figures with Consistent Theme

**Pick a theme early. Stick to it. 300 DPI minimum.**

Theme elements to decide upfront:
- **Color palette** — Pick 4-6 colors from a palette generator (colorbrewer2.org, coolors.co)
- **Background** — Dark or light (consistent across all figures)
- **Font** — Pick one font, minimum 10-11pt size
- **DPI** — 300 for PDF (print quality), 150+ for PNG (web)
- **Format** — Export both PDF (vector) and PNG (raster) for every figure

**Why:** Regenerating figures because of inconsistent themes wastes time. Pick colors once, hardcode them in your plotting config, and stick to them.

**Common mistake:** Using matplotlib's default colors. They're not designed for publication. Pick a professional palette and hardcode it.

---

### 3.3 Create Paper Tables in Markdown

**Generate LaTeX tables from JSON, but also make markdown versions for easy reference.**

Example:
```markdown
| Model | Method | Layer | Multiplier | Coherent Refusal | Garbled | Normal |
|-------|--------|-------|-----------|-----------------|---------|---------|
| Qwen 3B | DIM | L21 (60%) | 15× | 100% | 0% | 0% |
| Qwen 7B | DIM | L16 (60%) | 15× | 100% | 0% | 0% |
| Qwen 14B | DIM | L28 (60%) | 15× | 90% | 10% | 0% |
| Qwen 32B | DIM | L32 (50%) | 15× | 77% | 23% | 0% |
```

We stored these in `paper/tables/` and generated LaTeX via:
```python
import pandas as pd
df = pd.read_csv("table_data.csv")
print(df.to_latex(index=False))
```

**Why:** Reviewers ask questions like "what was the refusal rate for Gemma 2B at L7 again?" If you have a markdown table, you grep and answer in 10 seconds. If it's only in LaTeX, you compile and search the PDF.

---

### 3.4 Audit Data Against Logs

**Catch discrepancies early, before reviewers do.**

Audit checklist:
- **Parameter consistency:** Grep result files for experimental parameters. Check for inconsistencies (different sample sizes, mixed conditions, etc.)
- **Metric validation:** Spot-check 10+ conditions by recomputing metrics from raw outputs. Verify they match logged values.
- **File vs log comparison:** Compare values in structured files against raw logs. Catch logging bugs or stale data.
- **Recomputation validation:** Recompute derived metrics (if you saved intermediate data). Verify they match reported values.

**Why:** Data errors compound. If your result files are wrong, your tables are wrong, your figures are wrong, your claims are wrong. Audit before writing the paper.

**Lesson:** Reviewers will find discrepancies you miss. Catch them yourself first.

---

## Phase 4: Paper Writing

### 4.1 Start with Outline

**Don't write the paper linearly. Write the skeleton first.**

Our outline process (from `PAPER_OUTLINE.md`):
1. **Section structure** — 1. Abstract → 2. Intro → 3. Quick Tour → ... → 12. Conclusion
2. **Key claims per section** — "Section 5.2 claims: DIM matches COSMIC at all scales, COSMIC automated layer selection fails at 32B"
3. **Figures per section** — "Section 5.2 uses Figure 3 (bar chart: DIM vs COSMIC refusal rate)"
4. **Tables per section** — "Section 5.2 uses Table 4 (full DIM vs COSMIC comparison)"

We wrote the outline first, got Professor sign-off, THEN drafted prose.

**Why:** We revised the outline 2 times before writing a word. Each revision caught structural issues:
- First draft: Results before Methods. Professor said "reader needs Methods to understand Results." Swapped.
- Second draft: Discussion after Limitations. Professor said "Discussion should interpret results while they're fresh." Moved.

**Lesson:** Revising an outline takes 10 minutes. Revising a drafted paper takes 2 hours. Structure first, prose second.

---

### 4.2 Literature Review as Standalone Doc

**Write it separately, before the paper. Then distill into Background & Related Work.**

Process:
1. Write comprehensive `LITERATURE_REVIEW.md` (all papers, full summaries)
2. Use it to frame your contribution and identify the gap
3. Extract 2-3 pages for the paper's Background section
4. Keep the full review in your repo for reference

**Why:** A thorough literature review helps you:
- Frame your contribution clearly (what's new vs what's borrowed)
- Cite the right papers (give credit, avoid overclaiming)
- Identify gaps your work fills
- Catch if someone already did your experiment

---

### 4.3 Draft in Stages

**Methods/Results first (factual), then Intro/Discussion (interpretive).**

Our order:
1. **Methods** (§4-5) — What we did, in enough detail to reproduce
2. **Results** (§6-8) — What we found, with inline interpretation
3. **Discussion** (§9-11) — Why it happened, mechanistic hypotheses, implications
4. **Intro** (§1-3) — Framing, motivation, preview of findings
5. **Abstract** — One paragraph distilling the whole paper
6. **Conclusion** (§12) — Restate findings, future work

**Why:** Writing Intro before you have results is guessing. You don't know what the findings are yet. You'll end up rewriting it.

**Lesson:** You can't write a good introduction to results you don't have yet. Methods/Results are straightforward (describe what you did). Intro/Discussion require synthesis. Do easy first.

---

### 4.4 Multi-Round Review Process

**Four passes, each with a different lens.**

**Pass 1: Self-review for accuracy (Ghost)**
- Check every number against FINAL_RESULTS.json
- Verify citations exist and are formatted correctly
- Confirm figure/table references match actual figures/tables
- Flag any "we find X" claims without supporting data

**Pass 2: Deep critical review (simulated hostile reviewer)**
- Data consistency audit (do different tables/sections show the same numbers for the same conditions?)
- Apples-to-oranges detection (are you comparing conditions that differ in multiple ways?)
- Overclaiming detection ("our method is best" vs "we observe that on our test set...")
- Contradiction hunting (does Appendix say the opposite of Methods?)

Use a `DEEP_REVIEW.md` checklist. This pass typically finds 10-20 issues requiring fixes.

**Pass 3: Style guide pass (kill AI slop)**
- Em dash hunt (use sparingly, replace with commas or periods)
- Forbidden words: "notably," "furthermore," "it's worth noting," "novel," "comprehensive"
- Question-answer teasers ("What happens when...? The answer is...")
- Self-congratulation ("our groundbreaking work," "more interesting than...")

Use a `STYLE_GUIDE.md` checklist. Run automated grep for forbidden words. Typical findings:
- Question-answer teasers in intro
- Self-assessment language ("more interesting", "more informative")
- Boilerplate phrases ("fill a gap in the literature")
- Excessive em dashes (replace most with periods or commas)

**Pass 4: Final proofread (Professor + Sohail)**
- Read the whole paper aloud (catches awkward phrasing)
- Check that figures are readable (labels big enough, colors distinct)
- Verify appendices are populated (not "[To be populated]")
- LaTeX compilation test (pdflatex → bibtex → pdflatex → pdflatex)

**Why:** Each pass catches different errors. Pass 1 catches factual errors. Pass 2 catches logical errors. Pass 3 catches voice errors. Pass 4 catches everything else.

**Lesson:** You cannot do all four in one pass. Your brain doesn't work that way. Separate passes, different days if possible.

---

### 4.5 Voice Rules

**From `research-paper-style-guide.md` (Anthropic-inspired):**

**✅ DO:**
- Use first person: "We find," "our results," "we observe"
- Hedge appropriately: "suggests," "consistent with," "one possible explanation"
- State uncertainty: "We don't know why," "This remains an open question"
- Label speculation: "Hypothesis (untested):" or "One speculative interpretation:"
- Connect to mechanism: "This pattern would arise if the model implements refusal via X"
- Use footnotes for caveats: "We use 15× multiplier for Qwen models¹" [¹Gemma requires 25× due to...]

**❌ DON'T:**
- "Furthermore," "Moreover," "Notably," "It's worth noting"
- "Novel," "Comprehensive," "Robust" (unless technical meaning)
- "Our groundbreaking/pioneering/seminal work"
- "We fill a gap in the literature" (show the gap, don't declare it)
- Question-answer teasers: "What is steering? Steering is..."
- Em dashes for everything (use commas, parentheses, or separate sentences)
- Tell the reader what to think: "Our most interesting finding is..."

**Why:** AI slop is easy to spot. Reviewers skim the abstract for forbidden words. If they see "Furthermore, our novel method comprehensively demonstrates...", they assume it's GPT-generated and dismiss it.

**Lesson:** Let the results speak. If your finding is interesting, the reader will notice. You don't need to tell them.

---

## Phase 5: Publication Pipeline

### 5.1 LaTeX Compilation Checklist

**Standard bibliography pipeline:**

```bash
pdflatex main.tex     # First pass: resolve references
bibtex main           # Process bibliography
pdflatex main.tex     # Second pass: insert citations
pdflatex main.tex     # Third pass: resolve citation references
```

**Common overfull hbox warnings (fixed by):**
- Breaking long URLs with `\url{...}` (allows line breaks)
- Shortening captions or using abbreviations
- Rewording to avoid long unbreakable strings

**Common LaTeX errors:**
- `Undefined control sequence \citep` → Missing citation package (`natbib`, `biblatex`, etc.)
- `Bibliography not found` → Wrong `.bib` filename in `\bibliography{}`
- `Figure not found` → Path issue (check relative paths match directory structure)

---

### 5.2 Clean Public Repo

**Run a security scan before publishing:**

```bash
# Check for API keys, tokens, credentials (adapt patterns to your services)
grep -r "sk-" . --exclude-dir=.git
grep -r "api_key" . --exclude-dir=.git
grep -r "token" . --exclude-dir=.git
grep -r "secret" . --exclude-dir=.git

# Check for personal paths and usernames
grep -r "/Users/yourname" . --exclude-dir=.git
grep -r "yourusername" . --exclude-dir=.git
```

Common leaks to check for:
- API keys in notebooks, scripts, or config files
- Absolute paths with your username
- Authentication tokens
- `.env` files committed to git

**Recommended repo structure:**
```
experiment-name/
├── README.md
├── LICENSE
├── src/ (code)
├── results/ (data)
├── paper/ (PDF)
├── notebooks/ (analysis)
├── figures/ (plots)
└── docs/ (reproduction guide)
```

**README.md must have:**
- [ ] One-sentence description
- [ ] Installation instructions
- [ ] Reproduction instructions
- [ ] Citation (once published)
- [ ] License

**Lesson:** Scan before every public push. Secrets are easy to leak, embarrassing to retract.

---

### 5.3 Website: Research Page Entry

**Add to your personal/lab website:**

Include:
- **Title** — Paper title (linked to PDF)
- **Abstract** — 2-3 sentence summary
- **Links** — PDF, GitHub repo, web version (if applicable), arXiv (when available)
- **Date** — Month and year

**Before editing:** Verify your site's framework conventions (Jekyll, Hugo, Pelican, etc.). Check existing research entries for formatting patterns. Don't assume—verify.

---

### 5.4 Web Version (Optional)

**Web-native format for better accessibility.**

If creating a web version:
- Use a template designed for academic papers (Distill, Tufte CSS, etc.)
- Include both static images (PNG) and interactive figures (if applicable)
- Format bibliography consistently with the template
- Use relative paths for all assets

**Why:** PDFs are for print and archival. Web papers are more accessible, searchable, and allow interactive visualizations.

**Testing:**
- Test on mobile (font size, figure readability)
- Test all links (citations, figures, external references)
- Verify figure paths work (relative vs absolute)

---

### 5.5 arXiv Submission Checklist

**We haven't submitted yet, but here's the checklist:**

- [ ] PDF compiles cleanly (no warnings except overfull hbox, if unavoidable)
- [ ] All figures embedded (not external links)
- [ ] Bibliography complete (no "???" citations)
- [ ] Appendices included
- [ ] Author names + affiliations correct
- [ ] Abstract <250 words (arXiv limit: 1920 characters)
- [ ] License declared (we use CC BY 4.0)
- [ ] Source files uploaded (.tex, .bib, figures, .sty if custom)
- [ ] Category selected (cs.LG for us)
- [ ] Comments field populated (e.g., "28 pages, 8 figures, 6 tables")

**Why:** arXiv rejects for weird reasons. Common causes:
- Missing figure files
- Custom .sty file not uploaded
- Author name typos (they check ORCID)
- Abstract too long

**Lesson:** Do a test upload to arXiv's submission system. It'll catch most issues before the real submit.

---

## Domain-Specific Lessons

**This section has been moved.**

For domain-specific gotchas, tooling issues, and experiment-specific advice, see each experiment's `LESSONS_LEARNED.md` file.

**Example:** For activation steering experiments, see:
`experiments/llm-adversarial-psych-phase1-lit-review/LESSONS_LEARNED.md`

---

## Universal Lessons Summary

**These are the core lessons that apply across research domains:**

**1. Validate tooling on known-good configurations first**
- Different extraction tools can produce different results
- Always test your pipeline on a configuration with known expected outcomes
- Catches tooling bugs before they corrupt your data

**2. Pick evaluation parameters once and stick to them**
- Sample size, decoding strategy, metrics — choose upfront
- Changing mid-experiment makes results incomparable
- Consistency > optimization

**3. Structured files are source of truth, not dashboards**
- Dashboards can cache stale data or fail to sync
- Always save complete data to version-controlled files
- Dashboards for monitoring, files for provenance

**4. Appendix content must match Methods section**
- Contradictions between sections are reviewer magnets
- Cross-check all claims across document
- Generate from same source-of-truth data when possible

**5. Verify framework/tooling before making changes**
- Don't assume conventions (web framework, citation style, etc.)
- Check existing patterns or documentation
- Sub-agents can make incorrect assumptions—verify their output

**6. Budget tracking prevents nasty surprises**
- Track spending after every run
- Compare remaining budget to remaining work
- Cut low-priority experiments early if budget tight

**7. Document trade-offs explicitly**
- Every experimental choice has trade-offs (e.g., deterministic vs statistical power)
- Document them in your write-up
- Helps reviewers understand your decisions

**8. Em dashes are often a crutch**
- Most em dashes should be commas, periods, or parentheses
- Overuse makes writing feel fragmented
- Audit and reduce in editing

**9. Ban AI-slop keywords**
- "Notably," "furthermore," "moreover" signal AI-generated text
- Use a linter to catch them: `grep -E "notably|furthermore|moreover" paper.tex`
- Write in plain, direct language

**10. Question-answer teasers belong in blogs, not papers**
- Start with the claim, not a rhetorical question
- Research papers are direct, not teasing

**11. Show gaps, don't declare them**
- "We fill a gap" is boilerplate—show the gap instead
- Compare prior work systematically, let the gap emerge

**12. Negative results are findings**
- Promote failures from footnotes to findings
- Analyze them thoroughly
- Honest negative results strengthen papers

**13. Multiple reviewers catch different errors**
- Different people catch different classes of errors
- Technical reviewer for accuracy, writing expert for voice, domain expert for framing
- One pass is never enough

**14. Limitations should be specific and honest**
- Vague: "Future work could explore X"
- Specific: "Our analysis is limited to Y because Z. Extrapolating to W is speculative."
- Reviewers respect honest acknowledgment of limitations

---

## Summary: The Non-Negotiables

If you take nothing else from this guide, take these 10 rules:

1. **Write the experiment plan before running anything.** Revise it until someone smarter than you signs off.
2. **Pick canonical evaluation protocol (sample size, decoding, metrics) and never change it mid-stream.**
3. **Run a control test before every new experiment.** If the control fails, your setup is broken.
4. **Build shared utilities first. Test them before using them.**
5. **Log everything to JSON. W&B is for dashboards, JSON is for truth.**
6. **Document anomalies the day you find them.** Don't wait for paper writing.
7. **Audit data against logs before writing.** Catch contradictions before reviewers do.
8. **Draft Methods/Results first, Intro/Discussion last.** You can't introduce results you don't have.
9. **Four review passes: accuracy, logic, voice, polish.** Each catches different errors.
10. **Scan for secrets before pushing to GitHub.** `grep -r "sk-" .` is your friend.

Follow these, and you'll avoid 90% of the pain we went through.

---

*End of guide. Go forth and experiment wisely.*
