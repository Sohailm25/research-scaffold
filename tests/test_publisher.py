# ABOUTME: Tests for the publication pipeline module.
# ABOUTME: Covers HTML generation, LaTeX compilation, figure preparation, website deployment, and index updates.

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scaffold.publisher import (
    CompileResult,
    DeployResult,
    PublishConfig,
    compile_latex,
    deploy_to_website,
    generate_distill_html,
    prepare_figures,
    publish,
    update_research_index,
)


# ---------------------------------------------------------------------------
# PublishConfig dataclass
# ---------------------------------------------------------------------------


class TestPublishConfig:
    """Tests for the PublishConfig dataclass."""

    def test_required_fields(self):
        cfg = PublishConfig(experiment_root=Path("/tmp/exp"))
        assert cfg.experiment_root == Path("/tmp/exp")

    def test_default_website_repo_url(self):
        cfg = PublishConfig(experiment_root=Path("/tmp/exp"))
        assert cfg.website_repo_url == ""

    def test_default_website_local_path(self):
        cfg = PublishConfig(experiment_root=Path("/tmp/exp"))
        assert cfg.website_local_path == Path.home() / ".scaffold" / "website-repo"

    def test_default_author(self):
        cfg = PublishConfig(experiment_root=Path("/tmp/exp"))
        assert cfg.author == "Sohail Mohammad"

    def test_custom_values(self):
        cfg = PublishConfig(
            experiment_root=Path("/my/exp"),
            website_repo_url="https://github.com/user/site",
            website_local_path=Path("/site"),
            author="Jane Doe",
        )
        assert cfg.website_repo_url == "https://github.com/user/site"
        assert cfg.website_local_path == Path("/site")
        assert cfg.author == "Jane Doe"


# ---------------------------------------------------------------------------
# generate_distill_html
# ---------------------------------------------------------------------------


class TestGenerateDistillHtml:
    """Tests for Distill HTML generation from template."""

    def _make_sections(self):
        return [
            {"heading": "Introduction", "id": "intro", "content": "<p>Hello world.</p>"},
            {"heading": "Methods", "id": "methods", "content": "<p>We did stuff.</p>"},
        ]

    def _make_figures(self):
        return [
            {
                "path": "fig1.png",
                "caption": "The main result showing X.",
                "alt_text": "Bar chart of X",
                "number": 1,
            },
        ]

    def _make_references(self):
        return [
            {
                "number": 1,
                "authors": "Smith, J. and Doe, A.",
                "year": 2024,
                "title": "On Testing Things",
                "journal": "Journal of Tests",
                "doi": "10.1234/test",
            },
        ]

    def test_returns_string(self):
        html = generate_distill_html(
            title="My Paper",
            description="A short desc",
            abstract="This is the abstract.",
            sections=self._make_sections(),
        )
        assert isinstance(html, str)

    def test_contains_title(self):
        html = generate_distill_html(
            title="My Paper Title",
            description="desc",
            abstract="abstract text",
            sections=self._make_sections(),
        )
        assert "My Paper Title" in html

    def test_contains_abstract(self):
        html = generate_distill_html(
            title="T",
            description="D",
            abstract="This is a very important abstract.",
            sections=[],
        )
        assert "This is a very important abstract." in html

    def test_contains_sections(self):
        sections = self._make_sections()
        html = generate_distill_html(
            title="T",
            description="D",
            abstract="A",
            sections=sections,
        )
        assert "Introduction" in html
        assert "Methods" in html
        assert "<p>Hello world.</p>" in html
        assert 'id="intro"' in html
        assert 'id="methods"' in html

    def test_contains_everforest_css_vars(self):
        html = generate_distill_html(
            title="T", description="D", abstract="A", sections=[]
        )
        assert "--ef-bg:" in html
        assert "--ef-green:" in html
        assert "--ef-text:" in html
        assert "--ef-aqua:" in html

    def test_contains_toc_script(self):
        html = generate_distill_html(
            title="T", description="D", abstract="A", sections=[]
        )
        assert "toc-list" in html
        assert "querySelectorAll" in html

    def test_renders_figures(self):
        html = generate_distill_html(
            title="T",
            description="D",
            abstract="A",
            sections=[],
            figures=self._make_figures(),
        )
        assert "fig1.png" in html
        assert "The main result showing X." in html
        assert "Bar chart of X" in html
        assert "Figure 1." in html

    def test_renders_references(self):
        html = generate_distill_html(
            title="T",
            description="D",
            abstract="A",
            sections=[],
            references=self._make_references(),
        )
        assert "Smith, J. and Doe, A." in html
        assert "2024" in html
        assert "On Testing Things" in html
        assert "10.1234/test" in html

    def test_no_figures_no_crash(self):
        html = generate_distill_html(
            title="T", description="D", abstract="A", sections=[]
        )
        # Should not contain <figure> tags when no figures provided
        assert "<figure>" not in html

    def test_no_references_no_crash(self):
        html = generate_distill_html(
            title="T", description="D", abstract="A", sections=[]
        )
        # Should not contain references section
        assert "references" not in html.lower() or "References" not in html

    def test_custom_author(self):
        html = generate_distill_html(
            title="T",
            description="D",
            abstract="A",
            sections=[],
            author="Jane Doe",
        )
        assert "Jane Doe" in html

    def test_default_author(self):
        html = generate_distill_html(
            title="T", description="D", abstract="A", sections=[]
        )
        assert "Sohail Mohammad" in html

    def test_description_in_front_matter(self):
        html = generate_distill_html(
            title="T",
            description="A one-line summary",
            abstract="A",
            sections=[],
        )
        assert "A one-line summary" in html


# ---------------------------------------------------------------------------
# compile_latex (mocked subprocess)
# ---------------------------------------------------------------------------


class TestCompileLatex:
    """Tests for LaTeX compilation with mocked subprocess."""

    def test_missing_main_tex(self, tmp_path):
        result = compile_latex(tmp_path)
        assert result.success is False
        assert "main.tex not found" in result.log_output

    def test_returns_compile_result(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            # Create the expected PDF output
            (tmp_path / "main.pdf").touch()
            result = compile_latex(tmp_path)
        assert isinstance(result, CompileResult)

    def test_correct_command_sequence(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        (tmp_path / "main.pdf").touch()
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            compile_latex(tmp_path)

        assert mock_run.call_count == 4
        calls = mock_run.call_args_list
        assert calls[0][0][0] == ["pdflatex", "-interaction=nonstopmode", "main.tex"]
        assert calls[1][0][0] == ["bibtex", "main"]
        assert calls[2][0][0] == ["pdflatex", "-interaction=nonstopmode", "main.tex"]
        assert calls[3][0][0] == ["pdflatex", "-interaction=nonstopmode", "main.tex"]

    def test_success_when_pdf_exists(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        (tmp_path / "main.pdf").touch()
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="compiled", stderr="")
            result = compile_latex(tmp_path)
        assert result.success is True

    def test_failure_on_pdflatex_error(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="error", stderr="fatal")
            result = compile_latex(tmp_path)
        assert result.success is False
        assert "error" in result.log_output

    def test_command_not_found(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pdflatex not found")
            result = compile_latex(tmp_path)
        assert result.success is False
        assert "not found" in result.log_output.lower()

    def test_timeout(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{article}")
        with patch("scaffold.publisher.subprocess.run") as mock_run:
            import subprocess as sp

            mock_run.side_effect = sp.TimeoutExpired(cmd="pdflatex", timeout=120)
            result = compile_latex(tmp_path)
        assert result.success is False
        assert "timed out" in result.log_output.lower()


# ---------------------------------------------------------------------------
# prepare_figures
# ---------------------------------------------------------------------------


class TestPrepareFigures:
    """Tests for copying figure files to output directory."""

    def test_copies_png_from_figures_dir(self, tmp_path):
        exp = tmp_path / "experiment"
        figs = exp / "figures"
        figs.mkdir(parents=True)
        (figs / "fig1.png").write_bytes(b"PNG_DATA")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert len(result) == 1
        assert (out / "fig1.png").exists()
        assert (out / "fig1.png").read_bytes() == b"PNG_DATA"

    def test_copies_png_from_paper_figures_dir(self, tmp_path):
        exp = tmp_path / "experiment"
        pfigs = exp / "paper" / "figures"
        pfigs.mkdir(parents=True)
        (pfigs / "fig2.png").write_bytes(b"PNG2")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert len(result) == 1
        assert (out / "fig2.png").exists()

    def test_copies_from_both_dirs(self, tmp_path):
        exp = tmp_path / "experiment"
        (exp / "figures").mkdir(parents=True)
        (exp / "figures" / "a.png").write_bytes(b"A")
        (exp / "paper" / "figures").mkdir(parents=True)
        (exp / "paper" / "figures" / "b.png").write_bytes(b"B")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert len(result) == 2
        assert (out / "a.png").exists()
        assert (out / "b.png").exists()

    def test_skips_non_image_files(self, tmp_path):
        exp = tmp_path / "experiment"
        figs = exp / "figures"
        figs.mkdir(parents=True)
        (figs / "fig.png").write_bytes(b"PNG")
        (figs / "data.csv").write_text("a,b,c")
        (figs / "notes.txt").write_text("notes")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert len(result) == 1
        assert (out / "fig.png").exists()
        assert not (out / "data.csv").exists()

    def test_creates_output_dir(self, tmp_path):
        exp = tmp_path / "experiment"
        (exp / "figures").mkdir(parents=True)
        (exp / "figures" / "fig.png").write_bytes(b"PNG")

        out = tmp_path / "deep" / "nested" / "output"
        prepare_figures(exp, out)
        assert out.exists()

    def test_no_duplicates(self, tmp_path):
        """If same filename exists in both dirs, don't overwrite."""
        exp = tmp_path / "experiment"
        (exp / "figures").mkdir(parents=True)
        (exp / "figures" / "fig.png").write_bytes(b"FIRST")
        (exp / "paper" / "figures").mkdir(parents=True)
        (exp / "paper" / "figures" / "fig.png").write_bytes(b"SECOND")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        # Only one should be copied (first wins, no overwrite)
        assert len(result) == 1
        assert (out / "fig.png").read_bytes() == b"FIRST"

    def test_handles_jpg_and_svg(self, tmp_path):
        exp = tmp_path / "experiment"
        figs = exp / "figures"
        figs.mkdir(parents=True)
        (figs / "photo.jpg").write_bytes(b"JPG")
        (figs / "diagram.svg").write_bytes(b"SVG")

        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert len(result) == 2

    def test_empty_dirs(self, tmp_path):
        exp = tmp_path / "experiment"
        exp.mkdir(parents=True)
        out = tmp_path / "output"
        result = prepare_figures(exp, out)
        assert result == []


# ---------------------------------------------------------------------------
# deploy_to_website
# ---------------------------------------------------------------------------


class TestDeployToWebsite:
    """Tests for deploying experiment artifacts to website structure."""

    def _setup_experiment(self, tmp_path):
        """Create a minimal experiment directory with all required artifacts."""
        exp = tmp_path / "my-experiment"
        exp.mkdir()

        # Distill HTML
        distill = exp / "paper" / "distill"
        distill.mkdir(parents=True)
        (distill / "index.html").write_text("<html>distill</html>")
        distill_figs = distill / "figures"
        distill_figs.mkdir()
        (distill_figs / "fig1.png").write_bytes(b"FIG1")

        # PDF
        (exp / "paper").mkdir(exist_ok=True)
        (exp / "paper" / "main.pdf").write_bytes(b"PDF_DATA")

        return exp

    def test_creates_article_directory(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        result = deploy_to_website(exp, site, "Title", "Desc", 2026)
        article_dir = site / "content" / "extra" / "research" / "my-experiment"
        assert article_dir.exists()
        assert result.article_dir == article_dir

    def test_copies_distill_html(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        deploy_to_website(exp, site, "Title", "Desc", 2026)
        index = site / "content" / "extra" / "research" / "my-experiment" / "index.html"
        assert index.exists()
        assert index.read_text() == "<html>distill</html>"

    def test_copies_figures(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        deploy_to_website(exp, site, "Title", "Desc", 2026)
        fig = site / "content" / "extra" / "research" / "my-experiment" / "figures" / "fig1.png"
        assert fig.exists()
        assert fig.read_bytes() == b"FIG1"

    def test_copies_pdf(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        result = deploy_to_website(exp, site, "Title", "Desc", 2026)
        pdf = site / "content" / "papers" / "my-experiment-2026.pdf"
        assert pdf.exists()
        assert pdf.read_bytes() == b"PDF_DATA"
        assert result.pdf_path == pdf

    def test_returns_deploy_result(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        result = deploy_to_website(exp, site, "Title", "Desc", 2026)
        assert isinstance(result, DeployResult)
        assert result.success is True

    def test_handles_missing_distill_html(self, tmp_path):
        exp = tmp_path / "bare-experiment"
        exp.mkdir()
        (exp / "paper").mkdir()
        (exp / "paper" / "main.pdf").write_bytes(b"PDF")

        site = tmp_path / "website"
        site.mkdir()

        result = deploy_to_website(exp, site, "Title", "Desc", 2026)
        assert result.success is True
        # index.html should not exist since there was no distill source
        index = site / "content" / "extra" / "research" / "bare-experiment" / "index.html"
        assert not index.exists()

    def test_default_year(self, tmp_path):
        exp = self._setup_experiment(tmp_path)
        site = tmp_path / "website"
        site.mkdir()

        result = deploy_to_website(exp, site, "Title", "Desc")
        # Should use current year
        assert result.pdf_path.name.startswith("my-experiment-")


# ---------------------------------------------------------------------------
# update_research_index
# ---------------------------------------------------------------------------


class TestUpdateResearchIndex:
    """Tests for inserting entries into research.md."""

    def _make_research_md(self, tmp_path, content):
        md_path = tmp_path / "research.md"
        md_path.write_text(content)
        return md_path

    def test_inserts_positive_into_auto_research(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Recent Publications

Some publications here.

---

## Auto Research

Autonomous research publications generated via the research-scaffold harness.

---

## Other
""")
        update_research_index(
            md, "my-exp", "My Experiment", "Testing things", 2026, "positive"
        )
        content = md.read_text()
        assert "My Experiment" in content
        # Entry should be in Auto Research section
        auto_idx = content.index("## Auto Research")
        other_idx = content.index("## Other")
        entry_idx = content.index("My Experiment")
        assert auto_idx < entry_idx < other_idx

    def test_inserts_mixed_into_auto_research(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Auto Research

Autonomous research publications.

---
""")
        update_research_index(
            md, "exp2", "Mixed Result", "Mixed findings", 2026, "mixed"
        )
        content = md.read_text()
        assert "Mixed Result" in content

    def test_inserts_negative_into_negative_results(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Negative Results

Negative results that are still informative.

---
""")
        update_research_index(
            md, "neg-exp", "Null Finding", "No effect found", 2026, "negative"
        )
        content = md.read_text()
        assert "Null Finding" in content
        neg_idx = content.index("## Negative Results")
        entry_idx = content.index("Null Finding")
        assert neg_idx < entry_idx

    def test_creates_auto_research_section_if_missing(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Recent Publications

Some existing publications.

---

## Other Section
""")
        update_research_index(
            md, "new-exp", "New Paper", "New findings", 2026, "positive"
        )
        content = md.read_text()
        assert "## Auto Research" in content
        assert "New Paper" in content

    def test_creates_negative_results_section_if_missing(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Recent Publications

Publications.

---
""")
        update_research_index(
            md, "neg", "Neg Paper", "No effect", 2026, "negative"
        )
        content = md.read_text()
        assert "## Negative Results" in content
        assert "Neg Paper" in content

    def test_entry_contains_links(self, tmp_path):
        md = self._make_research_md(tmp_path, """\
# Research

## Auto Research

Auto research.

---
""")
        update_research_index(
            md, "cool-exp", "Cool Experiment", "Cool desc", 2026, "positive"
        )
        content = md.read_text()
        assert "/research/cool-exp/" in content
        assert "cool-exp-2026.pdf" in content
        assert "Sohail Mohammad" in content


# ---------------------------------------------------------------------------
# publish (integration)
# ---------------------------------------------------------------------------


class TestPublish:
    """Integration test for the full publish pipeline."""

    def _setup_full_experiment(self, tmp_path):
        """Create a fully populated experiment directory."""
        exp = tmp_path / "full-experiment"
        exp.mkdir()

        # Distill HTML and figures
        distill = exp / "paper" / "distill"
        distill.mkdir(parents=True)
        (distill / "index.html").write_text("<html>Full distill page</html>")
        dfigs = distill / "figures"
        dfigs.mkdir()
        (dfigs / "fig1.png").write_bytes(b"FIG1")
        (dfigs / "fig2.png").write_bytes(b"FIG2")

        # PDF
        (exp / "paper" / "main.pdf").write_bytes(b"FULL_PDF")

        # Website with research.md
        site = tmp_path / "website"
        pages = site / "content" / "pages"
        pages.mkdir(parents=True)
        (pages / "research.md").write_text("""\
# Research

## Recent Publications

Existing publications here.

---

## Other
""")
        return exp, site

    def test_creates_full_website_structure(self, tmp_path):
        exp, site = self._setup_full_experiment(tmp_path)
        result = publish(
            experiment_root=exp,
            website_path=site,
            title="Full Experiment",
            description="A complete experiment",
            abstract="This is the abstract",
            outcome="positive",
            year=2026,
        )
        assert result.success is True

        # Check article directory
        article = site / "content" / "extra" / "research" / "full-experiment"
        assert article.exists()
        assert (article / "index.html").exists()
        assert (article / "figures" / "fig1.png").exists()
        assert (article / "figures" / "fig2.png").exists()

        # Check PDF
        pdf = site / "content" / "papers" / "full-experiment-2026.pdf"
        assert pdf.exists()

        # Check research index updated
        research_md = site / "content" / "pages" / "research.md"
        content = research_md.read_text()
        assert "Full Experiment" in content
        assert "## Auto Research" in content

    def test_negative_outcome_uses_negative_section(self, tmp_path):
        exp, site = self._setup_full_experiment(tmp_path)
        publish(
            experiment_root=exp,
            website_path=site,
            title="Null Result",
            description="Nothing happened",
            abstract="Abstract",
            outcome="negative",
            year=2026,
        )
        research_md = site / "content" / "pages" / "research.md"
        content = research_md.read_text()
        assert "## Negative Results" in content
        assert "Null Result" in content

    def test_no_research_md_skips_index_update(self, tmp_path):
        exp = tmp_path / "exp"
        exp.mkdir()
        (exp / "paper" / "distill").mkdir(parents=True)
        (exp / "paper" / "distill" / "index.html").write_text("<html>test</html>")
        (exp / "paper" / "main.pdf").write_bytes(b"PDF")

        site = tmp_path / "website"
        site.mkdir()

        # No research.md -- should not crash
        result = publish(
            experiment_root=exp,
            website_path=site,
            title="T",
            description="D",
            abstract="A",
            year=2026,
        )
        assert result.success is True
