# Distill Page Style Guide

**Single source of truth for all research distill pages on sohailmo.ai.**

Last updated: 2026-02-20
Reference implementations: [Escape Velocity](/research/escape-velocity/), [FTLE](/research/ftle/), [Activation Steering](/research/activation-steering/)

---

## 1. Page Structure (required order)

```
d-front-matter (JSON: title, description, authors, katex)
d-title
  h1 (title)
  p (one-line subtitle/hook)
d-byline (auto-generated from front-matter)

div.page-layout
  aside.toc-rail > nav.toc-container (auto-populated by JS)
  d-article
    h2#abstract          — Abstract paragraph(s)
    div.note             — Reliability/methodology disclosure (if applicable)
    h2#why-this-matters  — "Why this matters" (1–2 paragraphs)
    h2#at-a-glance       — "At a glance" with 4 subsections:
      h3 "What we did"
      h3 "What we found"
      h3 "What this does NOT show"
      h3 "How to use this"
    h2 [core sections]   — Methods, results, analysis
    h2#decision-relevance — "Decision relevance" (what it shows / does NOT show)
    h2#limitations       — Limitations
    h2#references        — Manual references block (not d-bibliography)

d-appendix (optional)
```

**Non-negotiable:** Every page must have "Why this matters", "At a glance" (with all 4 subsections), and "What this does NOT show" sections.

---

## 2. Theme Tokens (Everforest Dark)

```css
:root {
    --ef-bg: #2d353b;        /* page background */
    --ef-bg-dim: #232a2e;    /* table headers, appendix, citation list */
    --ef-bg-card: #343f44;   /* cards, even table rows, note backgrounds */
    --ef-text: #d3c6aa;      /* primary text */
    --ef-text-muted: #859289; /* secondary text, captions, byline */
    --ef-green: #A7C080;     /* h1 title, h2 headings, note borders */
    --ef-green-dim: #859e7a; /* blockquote borders */
    --ef-aqua: #83C092;      /* links, h3 headings, sidenote numbers */
    --ef-blue: #7fbbb3;      /* accent (sparingly) */
    --ef-red: #e67e80;       /* warnings, failed gates */
    --ef-orange: #e69875;    /* accent */
    --ef-yellow: #dbbc7f;    /* accent */
    --ef-purple: #d699b6;    /* accent */
    --ef-border: #4a555b;    /* all borders and separators */
}
```

**Rules:**
- Page background: `--ef-bg` everywhere. No distinct header/section backgrounds.
- Borders: always `1px solid var(--ef-border)`. Never heavy/dark.
- Links: `--ef-aqua` default, `--ef-green` on hover.
- No harsh boxes or card-style containers for headers.

---

## 3. Header Treatment (d-title / d-byline)

```css
d-title {
    background-color: transparent;  /* SAME as page body */
    padding: 1.5em 0 1em;
    /* NO border-bottom — byline provides the separator */
}

d-byline {
    background-color: transparent;
    border-bottom: 1px solid var(--ef-border);  /* single subtle separator */
    padding-top: 0.8em;
    padding-bottom: 1.2em;
}
```

**Author/affiliation hierarchy:**
- Author names: `font-size: 1em; font-weight: 500`
- Affiliations: `font-size: 0.85em; opacity: 0.7; margin-top: 0.3em`
- Increased spacing between author name and affiliation rows

**Hide Distill auto-generated fields** (Published/DOI):
```css
d-byline .byline.grid > div:nth-child(2),
d-byline .byline.grid > div:nth-child(3) { display: none !important; }
```

---

## 4. Desktop Layout (≥1200px)

Two-column grid: left TOC rail + article body.

```css
@media (min-width: 1200px) {
    .page-layout {
        display: grid;
        grid-template-columns: 240px 1fr;
        gap: 40px;
        max-width: 1100px;
        margin: 0 auto;
        padding: 32px 24px 0;  /* top padding pushes both columns below banner */
    }
    d-article {
        max-width: 680px !important;
        margin-left: 0 !important;
        margin-right: auto !important;
        grid-column: 2 !important;
        grid-row: 1;
    }
}
```

**Title/byline alignment** (must match article column left edge):
```css
@media (min-width: 1200px) {
    d-title h1, d-title p.title-authors,
    d-title .title-authors, d-title p {
        margin-left: 106px !important;
    }
    d-byline .byline, d-byline .byline-container {
        margin-left: 106px !important;
    }
}
```

This 106px offset compensates for Distill's internal CSS grid (`grid-column: text`) which positions content ~106px left of where the article column starts under the rail layout. Verified at 1280px, 1440px, and 1920px (delta = 0 at all widths).

---

## 5. Left Rail TOC

**Desktop (≥1200px):** Fixed sticky sidebar.

```css
.toc-rail {
    grid-column: 1 !important;
    grid-row: 1;
    min-width: 0;
    margin-top: 48px;  /* breathing room from top banner */
}
.toc-container {
    position: sticky;
    top: 120px;
    max-height: calc(100vh - 144px);
    overflow-y: auto;
    background: transparent;
    border: 0;
    padding: 10px 0 0 0;  /* breathing room before first item */
    font-size: 0.85em;
}
```

**Mobile (<1200px):** Inline card fallback.

```css
.toc-container {
    background: var(--ef-bg-dim);
    border: 1px solid var(--ef-border);
    border-radius: 4px;
    padding: 1em 1.5em;
    margin: 1.5em 0 2em;
}
```

**TOC content rules:**
- No "Contents" heading (`.toc-container h3 { display: none; }`)
- No numbering (`list-style-type: none`)
- Muted text, aqua on hover
- Auto-populated by JS from h2 elements
- Two-column layout on mobile ≥600px, single column below

---

## 6. Right Rail Sidenotes (Tufte-style)

**When to use:** Methodological clarifications, statistical nuance, terminology definitions. NOT for core findings or caveats that must be in main text.

**Max length:** ~2 sentences. If longer, it belongs in the body.

**Markup pattern:**
```html
<label for="sn-PREFIX-NNN" class="sidenote-number"></label>
<input type="checkbox" id="sn-PREFIX-NNN" class="margin-toggle"/>
<span class="sidenote">Sidenote text here.</span>
```

- Prefix: `sn-ev-` (Escape Velocity), `sn-ftle-` (FTLE), `sn-as-` (Activation Steering)
- IDs are sequential: `sn-ev-001`, `sn-ev-002`, etc.
- **No `<d-cite>` tags inside sidenotes.** Distill's shadow DOM components break inside sidenotes. Use plain text citation references instead (e.g., "Eckmann & Ruelle, 1985").

**Desktop (≥1200px):** Float right, 240px wide, -280px right margin.

```css
.sidenote {
    float: right;
    clear: right;
    margin-right: -280px;
    width: 240px;
    font-size: 0.82em;
    line-height: 1.4;
    color: var(--ef-text-muted);
    border-left: 2px solid var(--ef-border);
    padding-left: 0.8em;
}
```

**Mobile (<1200px):** Hidden by default, checkbox-toggle collapsible.

```css
.sidenote {
    display: none;
    margin: 0.5em 0 0.5em 1em;
    padding: 0.5em 0.8em;
    background: var(--ef-bg-card);
    border-radius: 4px;
}
.margin-toggle:checked + .sidenote {
    display: block;
}
```

---

## 7. Typography & Spacing

| Element | Margin-top | Other |
|---------|-----------|-------|
| h2 | `1.2em` | `border-bottom: 1px solid var(--ef-border); padding-bottom: 0.3em; color: var(--ef-green)` |
| h3 | `0.8em` | `color: var(--ef-aqua)` |
| p | `0.8em` | — |
| figure | `1em` | — |
| table | `1em` | `font-size: 0.9em` |
| .note | `1em` | `border-left: 3px solid var(--ef-green); background: var(--ef-bg-card)` |
| blockquote | `1em` | `border-left: 3px solid var(--ef-green-dim); font-style: italic; color: var(--ef-text-muted)` |
| ul, ol | `0.5em` | — |

**Title:** `color: var(--ef-green)`. Distill h1 sizing (no override).
**Body text:** `color: var(--ef-text)` (Everforest `#d3c6aa`).
**Captions:** `font-size: 0.9em; color: var(--ef-text-muted)`.

---

## 8. Caption Rules

Every figure/table caption must follow the decision-relevant pattern:

```
<figcaption>
  <strong>Figure N.</strong> [Descriptive statement of what is shown].
  <em>[Decision-use statement: "If building X, this suggests Y,
  but note Z constraint/limitation."]</em>
</figcaption>
```

**Do:**
> **Figure 3.** Distribution of first-collapse turn index. Earlier peaks indicate faster deterioration. *If building multi-turn systems, this suggests where to place quality checkpoints, but note this reflects our 40-turn protocol with specific seed prompts, not arbitrary deployment conditions.*

**Don't:**
> Figure 3 shows the results. As we can see, the data confirms our hypothesis.

---

## 9. Claim Language Rules

### Non-causal framing lock (permanent)

**Always use:** "associated with", "conditional support", "predictive association", "consistent with", "we observe"

**Never use:** "predicts", "proves", "confirms mechanism", "validates", "demonstrates causation"

### Confidence calibration

| Claim type | Required syntax |
|-----------|----------------|
| Observation | "We observe..." |
| Association | "This is consistent with..." / "This is associated with..." |
| Boundary | "This does not establish..." |
| Decision relevance | "If building X, consider Y" |

### Section-level pacing (Anthropic/TML house style)

Every major section must follow this pattern:
1. **One-line stake** — why this section matters
2. **One-line result** — what we found
3. **One-line boundary** — what this doesn't show
4. **One-line decision relevance** — what to do with this

### "What this does NOT show" (required)

Every page must have an explicit section (in "At a glance" and optionally in "Decision relevance") listing what the study does NOT demonstrate. This is not optional.

---

## 10. Caveat Locks (permanent, never weaken)

These caveats are locked across all pages and any future edits:

| Caveat | Text pattern | Applies to |
|--------|-------------|-----------|
| κ reliability | "Cohen's κ = 0.566 vs. threshold 0.80; gate NOT MET" | Escape Velocity |
| Dependence structure | "predictor dependence structure not fully characterized" | FTLE |
| n/scope | "N conversations under fixed protocol; not arbitrary deployment" | All |
| LLM-rater circularity | "GPT-5.2 and Claude 4.6 Opus raters share potential biases" | All using LLM raters |
| Non-causal | "associated with, not caused by" | All |

---

## 11. Naming Locks (permanent)

| Internal name | Public name | Usage |
|--------------|-------------|-------|
| Paper A | Escape Velocity | All user-facing surfaces |
| Paper B | FTLE | All user-facing surfaces |

"Paper A" and "Paper B" must NEVER appear on any public page.

---

## 12. References

Use a **manual references block** (not `<d-bibliography>`). Distill's auto-bibliography renders `url` fields as `[link]` artifacts and has shadow DOM issues.

```html
<h2 id="references">References</h2>
<div class="references" style="font-size: 0.9em; color: var(--ef-text-muted); line-height: 1.6;">
<p>[1] Author, A. (Year). Title. <em>Journal</em>. DOI: <a href="...">...</a></p>
</div>
```

---

## 13. Do / Don't Examples

### ✅ Do

- "We observe that collapse rates vary by condition."
- "This is consistent with heterogeneous pairings reducing repetition."
- "This does not establish a causal mechanism."
- Use sidenotes for statistical nuance ("Cohen's κ accounts for chance agreement...")
- Transparent background on d-title/d-byline
- Pre-register success criteria before running

### ❌ Don't

- "Our results prove that..." / "This validates..."
- Em dashes anywhere (use commas, colons, periods, or parentheses)
- `<d-cite>` tags inside sidenotes
- Distinct background color on header (no box/card look)
- "Paper A" or "Paper B" in any user-facing text
- Cherry-picked examples without methodology disclosure
- Remove or weaken any locked caveat

---

## 14. Switzer-Style Add-on (4 KPI cards + findings dropdowns only)

Use this as an optional add-on inside `h2#at-a-glance` when you want high scanability.

### HTML pattern

```html
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Metric label</div>
    <div class="kpi-value">Primary number</div>
    <div class="kpi-note">Short context</div>
  </div>
  <!-- repeat to exactly 4 cards -->
</div>

<details class="finding" open>
  <summary>Finding 1 — headline insight</summary>
  <div class="finding-body">Expanded interpretation, caveat, and implication.</div>
</details>

<details class="finding">
  <summary>Finding 2 — secondary result</summary>
  <div class="finding-body">Expanded detail.</div>
</details>

<details class="finding">
  <summary>Finding 3 — boundary/deployment implication</summary>
  <div class="finding-body">Expanded detail.</div>
</details>
```

### CSS pattern

```css
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 1.1rem 0 1.6rem;
}
@media (max-width: 720px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
.kpi-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(211, 198, 170, 0.16);
  border-radius: 12px;
  padding: 14px 15px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
}
.kpi-label {
  color: var(--ef-text-muted);
  font-size: 0.8rem;
  letter-spacing: 0.02em;
  margin-bottom: 5px;
  text-transform: uppercase;
}
.kpi-value {
  color: var(--ef-text);
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.15;
}
.kpi-note {
  color: var(--ef-text-muted);
  font-size: 0.82rem;
  margin-top: 7px;
}

details.finding {
  background: rgba(255, 255, 255, 0.015);
  border: 1px solid rgba(211, 198, 170, 0.15);
  border-radius: 12px;
  margin: 9px 0;
  overflow: hidden;
}
details.finding summary {
  cursor: pointer;
  color: var(--ef-text);
  font-weight: 600;
  list-style: none;
  padding: 11px 14px;
  line-height: 1.35;
}
details.finding summary::-webkit-details-marker { display: none; }
details.finding summary::before {
  content: "▸";
  color: var(--ef-text-muted);
  font-weight: 700;
  margin-right: 8px;
}
details.finding[open] summary::before { content: "▾"; }
.finding-body {
  color: var(--ef-text-muted);
  padding: 10px 14px 12px;
  border-top: 1px solid rgba(211, 198, 170, 0.12);
  background: rgba(255, 255, 255, 0.01);
  margin-top: 0;
  line-height: 1.5;
}
```

### Rules

- Exactly 4 KPI cards.
- Open only the first finding by default.
- Findings headline stays concise; body includes implication + caveat.
- Keep this add-on limited to KPI cards and findings dropdowns only.

## 15. Non-Negotiable Defaults

1. **Everforest dark theme** with exact token values above
2. **Transparent header** (no box/card styling on d-title/d-byline)
3. **Left rail TOC** on desktop ≥1200px, inline card on mobile
4. **Right rail sidenotes** on desktop, checkbox-toggle on mobile
5. **"At a glance" section** with all 4 subsections (did/found/NOT/use)
6. **Non-causal claim language** everywhere
7. **Decision-relevant captions** on all figures/tables
8. **Locked caveats** never weakened in any edit
9. **No em dashes**
10. **Manual references block** (not d-bibliography)
11. **No "Paper A/B"** in user-facing copy
12. **Title/byline aligned** to article column on desktop
