# LaTeX Manuscript Style Guide

**Canonical formatting standard for all experiment manuscripts.**

Last updated: 2026-02-20
Reference implementations: `escape-velocity` main.tex, `ftle` main.tex, `activation-steering` main.tex

---

## 1. Document Class & Packages

```latex
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}          % professional tables
\usepackage{hyperref}
\usepackage[numbers]{natbib}   % numeric citations
\usepackage{microtype}         % typographic refinement
```

Use `booktabs` for all tables (no vertical rules, `\toprule`/`\midrule`/`\bottomrule` only). No `\hline`.

---

## 2. Manuscript Structure (required order)

```
\title{...}
\author{Sohail Mohammad \\ Independent Researcher}
\date{Preprint, 2026}
\maketitle

\begin{abstract} ... \end{abstract}

\section{Introduction}         — Stake, gap, contribution
\section{Related Work}         — Context (brief)
\section{Methods}              — Protocol, measurements, controls
\section{Results}              — Findings with tables/figures
\section{Discussion}           — Interpretation with boundaries
\section{Limitations}          — Explicit, never buried
\section{Conclusion}           — 1 paragraph, claim-calibrated
\section*{Acknowledgments}
\section*{Reproducibility Statement}  — REQUIRED
\bibliographystyle{plainnat}
\bibliography{references}
```

**Non-negotiable:** Every manuscript must have a standalone `Limitations` section and a `Reproducibility Statement`.

---

## 3. Section & Heading Style

- `\section{}` for major divisions (numbered)
- `\subsection{}` for sub-topics (numbered)
- `\paragraph{}` for inline emphasis points (unnumbered, bold run-in)
- No `\subsubsection` unless absolutely necessary
- Heading text: sentence case ("Results and discussion", not "Results And Discussion")

---

## 4. Claim Language Rules (permanent)

These rules match the distill style guide and apply identically to LaTeX manuscripts.

### Non-causal framing lock

| ✅ Use | ❌ Never use |
|--------|-------------|
| "associated with" | "predicts" |
| "consistent with" | "proves" |
| "we observe" | "confirms" |
| "conditional support" | "validates" |
| "predictive association" | "demonstrates causation" |

### Confidence calibration in text

- **Observation:** "We observe that X..."
- **Association:** "X is associated with Y (ρ = Z, p < 0.05)"
- **Boundary:** "This does not establish a causal mechanism"
- **Scope:** "Under these protocol conditions" / "Within the tested range"

### Limitation disclosure

Every results claim must be scoped. If a reliability gate failed, the failure must appear in:
1. The abstract
2. The results section
3. The limitations section
4. The conclusion

Never bury a negative gate result.

---

## 5. Table Style

```latex
\begin{table}[t]
\centering
\caption{Descriptive title with scope statement.
  \emph{Decision use: if building X, this suggests Y,
  but note Z constraint.}}
\label{tab:example}
\begin{tabular}{lcc}
\toprule
Condition & Metric A & Metric B \\
\midrule
Condition 1 & 0.42 & 0.78 \\
Condition 2 & 0.55 & 0.83 \\
\bottomrule
\end{tabular}
\end{table}
```

**Rules:**
- `booktabs` rules only (no `\hline`, no vertical rules)
- Caption above table
- Caption includes decision-relevance line in `\emph{}`
- Numeric values: consistent decimal places within a column
- Units in column headers, not repeated in cells

---

## 6. Figure Style

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/figure_name.pdf}
\caption{Descriptive statement of what is shown.
  \emph{Decision use: if building X, this suggests Y,
  but note Z constraint.}}
\label{fig:example}
\end{figure}
```

**Rules:**
- PDF or SVG preferred for vector graphics; PNG at ≥300 DPI for raster
- Caption below figure
- Caption includes decision-relevance line in `\emph{}`
- Reference as "Figure~\ref{fig:example}" (non-breaking space)
- All figures must be generated from the canonical matplotlib style file (see FIGURE_CHART_STYLE_GUIDE.md)

---

## 7. Citation & Bibliography

- Use `natbib` with `plainnat` style and numeric mode
- Cite as `\citep{key}` (parenthetical) or `\citet{key}` (textual)
- BibTeX file: `references.bib` in manuscript directory
- Every cited work must have: author, title, year, venue/journal
- DOI field required when available
- No URL-only citations (find the DOI)

---

## 8. Reproducibility Statement (required)

Every manuscript must end with:

```latex
\section*{Reproducibility Statement}

All code, data artifacts, and configuration files required to
reproduce the experiments in this paper are available at
\url{https://github.com/Sohailm25/REPO_NAME}. [Specific details
about frozen artifacts, commit hashes, seed policies, etc.]
```

Include:
- Public repo URL
- Key commit hash or release tag
- Seed policy description
- Hardware/compute environment
- Any frozen artifact hashes

---

## 9. Mathematical Notation

- Define all symbols on first use
- Use `\mathbf{}` for vectors, plain italic for scalars
- Use `\text{}` inside math for multi-letter subscripts: `$\lambda_{\text{max}}$`
- Align multi-line equations with `align` environment
- Number only equations referenced elsewhere

---

## 10. Pre-Submit Compile Checklist

- [ ] Compiles without errors (`pdflatex` + `bibtex` + `pdflatex` × 2)
- [ ] No undefined references or citations
- [ ] All figures render (no missing files)
- [ ] Abstract stands alone (no citations, no figure refs)
- [ ] Limitations section present and substantive
- [ ] Reproducibility statement present with repo URL
- [ ] No causal language violations (grep for "proves", "validates", "confirms mechanism")
- [ ] No em dashes (use `---` sparingly or rephrase)
- [ ] All locked caveats present and unweakened
- [ ] No "Paper A" or "Paper B" in text
- [ ] Page count within target (typically 7–12 pages)
- [ ] PDF metadata (title, author) set correctly

---

## 11. Non-Negotiable Defaults

1. `booktabs` tables with no vertical rules
2. Decision-relevant captions on all figures and tables
3. Non-causal claim language throughout
4. Standalone Limitations section (never buried in Discussion)
5. Reproducibility Statement with public repo link
6. All caveats carried through abstract → results → limitations → conclusion
7. Sentence-case headings
8. `natbib` with `plainnat` numeric style
