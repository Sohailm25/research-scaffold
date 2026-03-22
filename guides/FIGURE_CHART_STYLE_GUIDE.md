# Figure & Chart Style Guide

**Canonical styling standard for all experiment figures, charts, and visualizations.**

Last updated: 2026-02-20

---

## 1. Canonical Style File (source of truth)

```
experiments/compute-full-lyapunov-spectrum-production-transformer/
  paper-a-escape-velocity/paper/sohail_research.mplstyle
```

**Usage:**
```python
import matplotlib.pyplot as plt
plt.style.use('path/to/sohail_research.mplstyle')
```

All experiment figures MUST use this style file. Do not override its defaults unless the guide below explicitly permits it.

---

## 2. Color Palette

Derived from Everforest theme, darkened for white-background print contrast:

| Index | Hex | Name | Use |
|-------|-----|------|-----|
| 1 | `#4A7A5B` | Forest green | Primary data series |
| 2 | `#5A9BA3` | Teal | Secondary data series |
| 3 | `#C44D5E` | Coral red | Tertiary / warning / failed gates |
| 4 | `#7B6B8A` | Muted purple | Complement series |
| 5 | `#B8943E` | Warm amber | Complement series |
| 6 | `#2d353b` | Dark charcoal | Accent / reference lines |

**Rules:**
- Use colors in cycle order for multi-series plots
- Never use more than 5 data series on one plot (split into panels if needed)
- For binary comparisons: forest green (#1) vs coral red (#3)
- For baseline/reference lines: dark charcoal (#6), dashed
- Colorblind consideration: the palette avoids pure red/green adjacency, but always include shape/marker differentiation for accessibility

---

## 3. Typography (from style file)

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Axis labels | Inter / Helvetica | 11pt | 500 |
| Tick labels | Inter / Helvetica | 9pt | normal |
| Title | Inter / Helvetica | 12pt | 600 |
| Legend | Inter / Helvetica | 9pt | normal |
| Annotations | Inter / Helvetica | 9pt | normal |

- Font family: `Inter` preferred, `Helvetica Neue` fallback, `Arial` last resort
- All text: sans-serif

---

## 4. Axes & Grid

- **Remove top and right spines** (`axes.spines.top: False`, `axes.spines.right: False`)
- Spine width: 0.8pt, color `#4a555b`
- Grid: y-axis only by default, `#A7C080` at 12% opacity, 0.5pt
- Tick direction: outward
- Axis labels: sentence case ("Collapse rate", not "Collapse Rate")

---

## 5. Lines & Markers

- Line width: 2.0pt default
- Marker size: 7pt default
- For scatter plots: use distinct marker shapes per series (circle, square, triangle, diamond)
- For line plots: solid lines for primary, dashed for baselines/references

---

## 6. Confidence Intervals & Uncertainty

- **Always show uncertainty** when data supports it
- Preferred: shaded band (`fill_between`) at 95% CI
- Band opacity: 0.2–0.3
- Alternative: error bars with caps for discrete comparisons
- If bootstrap CI: state n_bootstrap in caption
- If no uncertainty available: state "point estimates only" in caption

---

## 7. Figure Caption Template

Every figure caption must follow:

```
Figure N. [Descriptive statement of what is shown].
[Decision-use statement: "If building X, this suggests Y,
but note Z constraint/limitation."]
```

**Do:**
> Figure 3. Distribution of first-collapse turn index across conditions. Earlier peaks indicate faster deterioration. *If building multi-turn systems, this suggests where to place quality checkpoints, but note this reflects our 40-turn protocol with specific seed prompts, not arbitrary deployment conditions.*

**Don't:**
> Figure 3. Results of our experiment showing the data.

---

## 8. Legend Rules

- No frame (`legend.frameon: False`)
- Place outside plot area if >3 entries; inside if ≤3
- Use `best` location for auto-placement, override manually if it obscures data
- Legend labels: descriptive, no abbreviations without prior definition

---

## 9. Export Specifications

| Format | Use | DPI | Notes |
|--------|-----|-----|-------|
| PDF | LaTeX manuscripts | vector | Preferred for all print |
| SVG | Web/distill pages | vector | Preferred for web |
| PNG | Fallback only | 300 | Only when vector not possible |

**Figure size:** 6.5 × 4.0 inches default (fits single-column LaTeX). For two-panel: 6.5 × 3.0 per panel.

**Save settings (from style file):**
```python
plt.savefig('figure.pdf', dpi=300, bbox_inches='tight', pad_inches=0.15,
            facecolor='white')
```

---

## 10. Multi-Panel Figures

- Use `matplotlib.gridspec` or `plt.subplots` for consistent spacing
- Shared axes where appropriate (shared x-axis for same metric)
- Panel labels: (a), (b), (c) in upper-left corner, bold, 11pt
- Each panel gets its own descriptive subtitle if content differs

---

## 11. Annotation Rules

- Use `ax.annotate()` with arrows for callouts
- Arrow style: `arrowprops=dict(arrowstyle='->', color='#4a555b', lw=1.0)`
- Annotation text: 9pt, same font family
- Threshold lines: dashed, dark charcoal (#6), with text label
- Statistical significance markers: `*` (p<0.05), `**` (p<0.01), `***` (p<0.001)

---

## 12. Non-Negotiable Defaults

1. Use `sohail_research.mplstyle` for all figures
2. Top and right spines removed
3. Uncertainty displayed when data supports it
4. Decision-relevant caption on every figure
5. PDF/SVG export (never raster-only for manuscripts)
6. ≤5 data series per plot
7. Colorblind-accessible: markers differentiate in addition to color
8. Sentence-case axis labels
9. No decorative elements (3D effects, gradients, shadows)
10. White background for all figures
