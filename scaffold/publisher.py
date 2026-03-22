# ABOUTME: Publication pipeline for deploying experiment results to website.
# ABOUTME: Generates Distill HTML, compiles LaTeX PDFs, and deploys to website repo.

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


@dataclass
class PublishConfig:
    """Configuration for publishing an experiment."""

    experiment_root: Path
    website_repo_url: str = ""
    website_local_path: Path = field(default_factory=lambda: Path.home() / ".scaffold" / "website-repo")
    author: str = "Sohail Mohammad"


@dataclass
class CompileResult:
    """Result of LaTeX compilation."""

    success: bool
    log_output: str


@dataclass
class DeployResult:
    """Result of deploying to website."""

    success: bool
    article_dir: Path
    pdf_path: Path
    message: str = ""


def generate_distill_html(
    title: str,
    description: str,
    abstract: str,
    sections: list[dict],
    figures: list[dict] | None = None,
    references: list[dict] | None = None,
    author: str = "Sohail Mohammad",
    acknowledgments: str = "",
    repo_url: str = "",
) -> str:
    """Generate a Distill-style HTML article from structured content.

    Args:
        title: Article title.
        description: One-line description for front matter.
        abstract: Abstract text.
        sections: List of dicts with keys: heading, id, content (HTML string).
        figures: List of dicts with keys: path, caption, alt_text, number.
        references: List of dicts with keys: number, authors, year, title, journal, doi.
        author: Author name.
        acknowledgments: Acknowledgments text.
        repo_url: Repository URL for reproducibility section.

    Returns:
        Rendered HTML string.
    """
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    template = env.get_template("distill.html.j2")

    return template.render(
        title=title,
        description=description,
        abstract=abstract,
        sections=sections,
        figures=figures or [],
        references=references or [],
        author=author,
        acknowledgments=acknowledgments,
        repo_url=repo_url,
    )


def compile_latex(paper_dir: Path) -> CompileResult:
    """Compile LaTeX manuscript: pdflatex -> bibtex -> pdflatex -> pdflatex.

    Expects paper_dir to contain main.tex.
    Returns a CompileResult with success flag and combined log output.
    """
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        return CompileResult(success=False, log_output=f"main.tex not found in {paper_dir}")

    commands = [
        ["pdflatex", "-interaction=nonstopmode", "main.tex"],
        ["bibtex", "main"],
        ["pdflatex", "-interaction=nonstopmode", "main.tex"],
        ["pdflatex", "-interaction=nonstopmode", "main.tex"],
    ]

    log_parts: list[str] = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(paper_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            log_parts.append(f"$ {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
            # bibtex may return 1 for warnings; only fail on pdflatex errors
            if cmd[0] == "pdflatex" and result.returncode != 0:
                return CompileResult(
                    success=False,
                    log_output="\n".join(log_parts),
                )
        except FileNotFoundError:
            return CompileResult(
                success=False,
                log_output=f"Command not found: {cmd[0]}",
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                log_output=f"Command timed out: {' '.join(cmd)}",
            )

    pdf_path = paper_dir / "main.pdf"
    return CompileResult(
        success=pdf_path.exists(),
        log_output="\n".join(log_parts),
    )


def prepare_figures(experiment_root: Path, output_dir: Path) -> list[Path]:
    """Copy image files from experiment to output directory.

    Looks in experiment_root/figures/ and experiment_root/paper/figures/.
    Returns list of copied file paths in the output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    image_extensions = frozenset((".png", ".jpg", ".jpeg", ".svg"))
    search_dirs = [
        experiment_root / "figures",
        experiment_root / "paper" / "figures",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for fig_file in sorted(search_dir.iterdir()):
            if fig_file.suffix.lower() in image_extensions:
                dest = output_dir / fig_file.name
                if not dest.exists():
                    shutil.copy2(fig_file, dest)
                    copied.append(dest)

    return copied


def deploy_to_website(
    experiment_root: Path,
    website_path: Path,
    title: str,
    description: str,
    year: int | None = None,
) -> DeployResult:
    """Deploy experiment artifacts to the website repo directory structure.

    Creates:
        content/extra/research/{name}/index.html (from paper/distill/index.html)
        content/extra/research/{name}/figures/ (from paper/distill/figures/)
        content/papers/{name}-{year}.pdf (from paper/main.pdf)
    """
    if year is None:
        year = datetime.now(timezone.utc).year

    experiment_name = experiment_root.name

    # Create article directory
    article_dir = website_path / "content" / "extra" / "research" / experiment_name
    article_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = article_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    # Copy Distill HTML
    distill_html = experiment_root / "paper" / "distill" / "index.html"
    if distill_html.exists():
        shutil.copy2(distill_html, article_dir / "index.html")

    # Copy distill figures
    distill_figs = experiment_root / "paper" / "distill" / "figures"
    if distill_figs.exists():
        for fig in distill_figs.iterdir():
            shutil.copy2(fig, figures_dir / fig.name)

    # Copy PDF
    papers_dir = website_path / "content" / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    pdf_src = experiment_root / "paper" / "main.pdf"
    pdf_dest = papers_dir / f"{experiment_name}-{year}.pdf"
    if pdf_src.exists():
        shutil.copy2(pdf_src, pdf_dest)

    return DeployResult(
        success=True,
        article_dir=article_dir,
        pdf_path=pdf_dest,
    )


def update_research_index(
    research_md_path: Path,
    experiment_name: str,
    title: str,
    description: str,
    year: int,
    outcome: str = "positive",
) -> None:
    """Insert an entry into the research.md page.

    For outcome "positive" or "mixed": inserts into "Auto Research" section.
    For outcome "negative": inserts into "Negative Results" section.
    Creates the target section if it does not exist.
    """
    content = research_md_path.read_text()

    entry = (
        f"\n### [{title}](/research/{experiment_name}/)\n"
        f"**{description}**\n\n"
        f"Sohail Mohammad - Preprint, {year}\n\n"
        f"[Distill page](/research/{experiment_name}/) - "
        f"[Paper (PDF)]({{{{static}}}}/papers/{experiment_name}-{year}.pdf) - "
        f"[Code (GitHub)](https://github.com/Sohailm25/{experiment_name})\n"
    )

    if outcome == "negative":
        target_section = "## Negative Results"
    else:
        target_section = "## Auto Research"

    if target_section in content:
        # Insert entry after the section header and any description paragraph
        section_idx = content.index(target_section)
        header_end = content.index("\n", section_idx)
        # Skip blank lines and description text until we hit content or next section
        insert_pos = header_end + 1
        lines = content[insert_pos:].split("\n")
        skip = 0
        for line in lines:
            if line.startswith("## ") or line.startswith("---"):
                break
            if line.startswith("### "):
                break
            skip += 1
        insert_pos += sum(len(line) + 1 for line in lines[:skip])
        content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
    else:
        # Create the section after "Recent Publications" or at the end
        if "## Recent Publications" in content:
            pub_idx = content.index("## Recent Publications")
            rest = content[pub_idx:]
            separator_positions = [
                i for i in range(1, len(rest)) if rest[i : i + 3] == "---"
            ]
            if separator_positions:
                insert_pos = pub_idx + separator_positions[0]
                section_block = (
                    f"\n---\n\n{target_section}\n\n"
                    f"Autonomous research publications generated via the research-scaffold harness.\n"
                    f"{entry}\n"
                )
                content = content[:insert_pos] + section_block + content[insert_pos:]
            else:
                content += (
                    f"\n---\n\n{target_section}\n\n"
                    f"Autonomous research publications generated via the research-scaffold harness.\n"
                    f"{entry}\n"
                )
        else:
            content += (
                f"\n---\n\n{target_section}\n\n"
                f"Autonomous research publications generated via the research-scaffold harness.\n"
                f"{entry}\n"
            )

    research_md_path.write_text(content)


def publish(
    experiment_root: Path,
    website_path: Path,
    title: str,
    description: str,
    abstract: str,
    outcome: str = "positive",
    year: int | None = None,
) -> DeployResult:
    """Full publication pipeline: deploy to website and update index.

    Assumes paper/distill/index.html and paper/main.pdf already exist.
    """
    if year is None:
        year = datetime.now(timezone.utc).year

    experiment_name = experiment_root.name

    # Deploy artifacts to website
    result = deploy_to_website(experiment_root, website_path, title, description, year)

    # Update research index if research.md exists
    research_md = website_path / "content" / "pages" / "research.md"
    if research_md.exists():
        update_research_index(
            research_md, experiment_name, title, description, year, outcome
        )

    return result
