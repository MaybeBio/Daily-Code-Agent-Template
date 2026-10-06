#!/usr/bin/env python3
"""
agents/report_generator.py
------------------------------------------------------------------------------
Report Generator for BioLitAgent.

Reads all approved items from storage/knowledge_store.db (read-only), groups
them into 8 report chapters, and writes a timestamped Word (.docx) digest.

DESIGN CONSTRAINTS
------------------
  READ-ONLY DB         This agent never writes to knowledge_store.db.
                       PRAGMA query_only = ON is set at connection open time;
                       any accidental write raises OperationalError immediately.

  NO REPORT OVERWRITE  Output is always a new timestamped file.  If a file for
                       today already exists, a 3-digit counter suffix is added.
                       Previously generated reports in reports/ are immutable.

  NO VERBATIM TEXT     Only the `description` column (a human-reviewed original
                       paraphrase) is placed in the document body.  Raw source
                       text, PDF content, and regulatory document excerpts are
                       never written into any output.

Chapter structure (13 taxonomy tags -> 8 report chapters)
----------------------------------------------------------
  Ch 1  Executive Summary - What's New
        Items reviewed_at > last_report.json timestamp  (all tags)
  Ch 2  Host, Plasmid & Expression System Development
        Tags: host_expression
  Ch 3  Process Development - Upstream & Downstream
        Tags: upstream_process, downstream_process
  Ch 4  Characterization, QbD & Control Strategy
        Tags: analytical_characterization, qbd_control_strategy
  Ch 5  Digital Process Tools & Hybrid Modeling
        Tags: hybrid_modeling
  Ch 6  GMP, Facility & Quality Systems
        Tags: gmp_manufacturing, facility_aseptic
  Ch 7  Regulatory, CMC & Platform Science
        Tags: regulatory_cmc, microbiome_platform_science
  Ch 8  CAPA, Root Cause Analysis & Emerging Topics
        Tags: capa_rca, emerging_topics

Usage
-----
  python agents/report_generator.py
  python agents/report_generator.py --since 2026-09-20T00:00:00+00:00
  python agents/report_generator.py --dry-run
  python agents/report_generator.py --list-chapters
  python agents/report_generator.py --db PATH --reports-dir PATH

Dependencies
------------
  pip install python-docx

Outputs
-------
  reports/biolitagent_digest_YYYYMMDD.docx   (new file, never overwritten)
  storage/last_report.json                   (updated after successful write)
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Optional: python-docx ─────────────────────────────────────────────────────
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn as _qn
    _DOCX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DOCX_AVAILABLE = False

# ── Optional: python-dotenv ───────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT             = Path(__file__).resolve().parent.parent
_DEFAULT_DB       = _ROOT / "storage" / "knowledge_store.db"
_REPORTS_DIR      = _ROOT / "reports"
_TEMPLATES_DIR    = _ROOT / "templates"
_TEMPLATE_FILE    = _TEMPLATES_DIR / "digest_template.docx"
_LAST_REPORT_FILE = _ROOT / "storage" / "last_report.json"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("report_generator")

# ── Chapter structure ──────────────────────────────────────────────────────────


@dataclass
class ChapterDef:
    number:       int
    title:        str
    tags:         list[str] = field(default_factory=list)
    is_whats_new: bool      = False


# 13 taxonomy tags mapped to 8 report chapters.
# Chapter 1 uses a time-filtered query (items since last report).
# Chapters 2-8 pull the FULL running set for their tag list.
CHAPTERS: list[ChapterDef] = [
    ChapterDef(1, "Executive Summary - What's New",
               [], is_whats_new=True),
    ChapterDef(2, "Host, Plasmid & Expression System Development",
               ["host_expression"]),
    ChapterDef(3, "Process Development - Upstream & Downstream",
               ["upstream_process", "downstream_process"]),
    ChapterDef(4, "Characterization, QbD & Control Strategy",
               ["analytical_characterization", "qbd_control_strategy"]),
    ChapterDef(5, "Digital Process Tools & Hybrid Modeling",
               ["hybrid_modeling"]),
    ChapterDef(6, "GMP, Facility & Quality Systems",
               ["gmp_manufacturing", "facility_aseptic"]),
    ChapterDef(7, "Regulatory, CMC & Platform Science",
               ["regulatory_cmc", "microbiome_platform_science"]),
    ChapterDef(8, "CAPA, Root Cause Analysis & Emerging Topics",
               ["capa_rca", "emerging_topics"]),
]


# ── DB helpers (read-only) ─────────────────────────────────────────────────────


def open_db_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Open knowledge_store.db with PRAGMA query_only = ON.

    This agent NEVER writes to the knowledge store.  The PRAGMA makes that
    constraint explicit at the SQLite driver level: any INSERT/UPDATE/DELETE
    call would immediately raise OperationalError.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            "knowledge_store.db not found: {}\n"
            "  Run review_checkpoint.py to approve items first.".format(db_path)
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def read_total_count(conn: sqlite3.Connection) -> int:
    """Return the total number of approved items in the knowledge store."""
    return conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0]


def read_items_since(
    conn:      sqlite3.Connection,
    since_iso: Optional[str],
) -> list[dict[str, Any]]:
    """
    Return approved items for Chapter 1 (What's New).

    If *since_iso* is None (first run), ALL items are returned.
    Otherwise, only items where reviewed_at > since_iso are returned.
    Results are sorted most-recent-first.
    """
    if since_iso is None:
        rows = conn.execute(
            "SELECT * FROM knowledge_items ORDER BY reviewed_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM knowledge_items WHERE reviewed_at > ? "
            "ORDER BY reviewed_at DESC",
            (since_iso,),
        ).fetchall()
    return _to_dicts(rows)


def read_items_by_tags(
    conn: sqlite3.Connection,
    tags: list[str],
) -> list[dict[str, Any]]:
    """
    Return ALL approved items whose chapter_tag is in *tags*.
    Results sorted most-recent-first.
    """
    if not tags:
        return []
    ph = ",".join("?" * len(tags))
    rows = conn.execute(
        "SELECT * FROM knowledge_items WHERE chapter_tag IN ({}) "
        "ORDER BY reviewed_at DESC".format(ph),
        tags,
    ).fetchall()
    return _to_dicts(rows)


# ── last_report.json helpers ──────────────────────────────────────────────────


def load_last_report_state(path: Path) -> dict[str, Any]:
    """Return the stored state, or defaults if the file does not exist."""
    if not path.exists():
        return {"last_generated_at": None, "last_report_file": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read %s — treating as first run.", path.name)
        return {"last_generated_at": None, "last_report_file": None}


def save_last_report_state(
    path:         Path,
    report_file:  Path,
    generated_at: str,
) -> None:
    """Write last_report.json with the new report's timestamp and file path."""
    state = {
        "last_generated_at": generated_at,
        "last_report_file":  str(report_file),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Updated %s  (last_generated_at=%s)", path.name, generated_at[:19])


# ── Word template creation ─────────────────────────────────────────────────────


def create_template_if_missing() -> None:
    """
    Create templates/digest_template.docx with standard styles if absent.

    The template sets page margins and adjusts Heading 1/2/Normal styles.
    Once created it is never overwritten; edit it manually to change the
    document design.
    """
    if _TEMPLATE_FILE.exists():
        return

    _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document()

    # Margins: 1.25 in left/right, 1.0 in top/bottom
    for section in doc.sections:
        section.top_margin    = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin   = Inches(1.25)
        section.right_margin  = Inches(1.25)

    # Heading 1 — chapter titles
    h1 = doc.styles["Heading 1"]
    h1.font.name       = "Calibri"
    h1.font.size       = Pt(15)
    h1.font.bold       = True
    h1.font.color.rgb  = RGBColor(0x1F, 0x45, 0x7C)   # dark blue

    # Heading 2 — sub-section headings
    h2 = doc.styles["Heading 2"]
    h2.font.name       = "Calibri"
    h2.font.size       = Pt(12)
    h2.font.bold       = True
    h2.font.color.rgb  = RGBColor(0x2E, 0x74, 0xB5)   # medium blue

    # Normal / body text
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    # Placeholder content (cleared when generating a report)
    doc.add_paragraph("[BioLitAgent Digest Template v1.0 — content auto-generated]")

    doc.save(str(_TEMPLATE_FILE))
    log.info("Created Word template: %s", _TEMPLATE_FILE)


# ── Document construction helpers ─────────────────────────────────────────────


def _clear_document_body(doc: "Document") -> None:
    """
    Remove all body paragraphs from *doc*, preserving styles and section
    properties (w:sectPr — page size, margins, orientation).
    """
    body = doc.element.body
    for child in list(body):
        if child.tag != _qn("w:sectPr"):
            body.remove(child)


def format_source_line(item: dict[str, Any]) -> str:
    """
    Build a short parenthetical citation string for *item*.

    Format: "Authors, Year, DOI, Source type"
    Example regulatory: "FDA, 2026-09-15, Regulatory"
    Example PDF:        "Smith J et al., 2026, DOI: 10.1234/test, PDF deposit"

    Only bibliographic metadata is used here — never source text.
    """
    try:
        meta: dict[str, Any] = json.loads(item.get("metadata_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}

    source = item.get("source_type", "")
    parts: list[str] = []

    if source == "regulatory":
        agency = meta.get("agency") or ""
        if agency:
            parts.append(agency)
        pub_date = (meta.get("publication_date") or "")[:10]
        if pub_date and not meta.get("date_unknown"):
            parts.append(pub_date)
        parts.append("Regulatory")

    elif source in ("deposited_pdf", "literature", "pubmed", "biorxiv"):
        authors: list[str] = meta.get("authors") or []
        if len(authors) == 1:
            parts.append(authors[0])
        elif len(authors) == 2:
            parts.append("{} & {}".format(authors[0], authors[1]))
        elif len(authors) > 2:
            parts.append("{} et al.".format(authors[0]))
        year = meta.get("publication_year")
        if year:
            parts.append(str(year))
        doi = meta.get("doi")
        if doi:
            parts.append("DOI: {}".format(doi))
        if source == "deposited_pdf":
            parts.append("PDF deposit")
        elif source == "pubmed":
            parts.append("PubMed")
        elif source == "biorxiv":
            parts.append("bioRxiv")
        else:
            parts.append("Literature")

    else:
        parts.append(source)

    return ", ".join(parts)


def _add_cover_page(
    doc:            "Document",
    generated_at:   str,
    since_iso:      Optional[str],
    total_items:    int,
    chapter_counts: dict[int, int],
) -> None:
    """Add the digest cover page to *doc*."""
    # Main title
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = title_p.add_run("BioLitAgent Literature Digest")
    tr.font.name      = "Calibri"
    tr.font.size      = Pt(24)
    tr.font.bold      = True
    tr.font.color.rgb = RGBColor(0x1F, 0x45, 0x7C)

    # Subtitle
    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sub_p.add_run("Bioprocess & Protein Production Monitoring Report")
    sr.font.name      = "Calibri"
    sr.font.size      = Pt(13)
    sr.font.color.rgb = RGBColor(0x59, 0x59, 0x59)

    doc.add_paragraph()  # spacer

    # Generation date
    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_p.add_run("Generated: {}".format(generated_at[:10]))

    # What's new cutoff
    period_p = doc.add_paragraph()
    period_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if since_iso:
        period_p.add_run("What's New since: {}".format(since_iso[:10]))
    else:
        period_p.add_run("What's New since: (first report — all items included)")

    # Item counts
    count_p = doc.add_paragraph()
    count_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    whats_new = chapter_counts.get(1, 0)
    count_p.add_run(
        "New this period: {}   |   Total in knowledge store: {}".format(
            whats_new, total_items
        )
    )

    doc.add_paragraph()  # spacer

    # Chapter outline
    hdr = doc.add_paragraph()
    hdr.add_run("Report Chapters:").bold = True

    for ch in CHAPTERS:
        n = chapter_counts.get(ch.number, 0)
        lp = doc.add_paragraph()
        lp.paragraph_format.left_indent = Inches(0.5)
        tags_str = (
            ", ".join(ch.tags) if ch.tags else "all items since last report"
        )
        lp.add_run(
            "{num}. {title}  ({n} item{s})".format(
                num=ch.number, title=ch.title,
                n=n, s="" if n == 1 else "s",
            )
        )

    doc.add_page_break()


def _add_item(doc: "Document", item: dict[str, Any]) -> None:
    """
    Add one knowledge-store item to the document as a formatted citation.

    Citation format (per specification):
        [bold]  Title Text  [normal, smaller]  (Authors, Year, Source)
                Paraphrased description — 2-3 sentences.
                [optional] [Reviewer note: ...]

    This function writes ONLY the description field, which was reviewed by a
    human and stored as an original paraphrase.  No raw source text, abstract,
    or verbatim regulatory content is ever written to the document.
    """
    # ── Citation line ──────────────────────────────────────────────────────
    cite_p = doc.add_paragraph()
    cite_p.paragraph_format.left_indent  = Inches(0.25)
    cite_p.paragraph_format.space_before = Pt(6)
    cite_p.paragraph_format.space_after  = Pt(0)

    title_run = cite_p.add_run(item.get("title") or "(no title)")
    title_run.bold      = True
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(11)

    source_line = format_source_line(item)
    if source_line:
        src_run = cite_p.add_run("  ({})".format(source_line))
        src_run.bold           = False
        src_run.font.name      = "Calibri"
        src_run.font.size      = Pt(10)
        src_run.font.color.rgb = RGBColor(0x59, 0x59, 0x59)

    # ── Description (paraphrase only) ─────────────────────────────────────
    description = (item.get("description") or "").strip()
    if description:
        desc_p = doc.add_paragraph()
        desc_p.paragraph_format.left_indent  = Inches(0.5)
        desc_p.paragraph_format.space_before = Pt(2)
        desc_p.paragraph_format.space_after  = Pt(10)
        dr = desc_p.add_run(description)
        dr.font.name = "Calibri"
        dr.font.size = Pt(11)

    # ── Reviewer note (if any) ─────────────────────────────────────────────
    note = (item.get("reviewer_note") or "").strip()
    if note:
        note_p = doc.add_paragraph()
        note_p.paragraph_format.left_indent  = Inches(0.5)
        note_p.paragraph_format.space_before = Pt(0)
        note_p.paragraph_format.space_after  = Pt(8)
        nr = note_p.add_run("[Reviewer note: {}]".format(note))
        nr.font.name       = "Calibri"
        nr.font.size       = Pt(10)
        nr.font.italic     = True
        nr.font.color.rgb  = RGBColor(0x70, 0x70, 0x70)


def _add_chapter(
    doc:       "Document",
    ch:        ChapterDef,
    items:     list[dict[str, Any]],
    since_iso: Optional[str],
) -> None:
    """Add one chapter heading, intro, and all its items to *doc*."""
    doc.add_heading(
        "{n}. {title}".format(n=ch.number, title=ch.title),
        level=1,
    )

    # Chapter intro line
    n = len(items)
    if ch.is_whats_new:
        if since_iso:
            intro = (
                "Items added to the knowledge store since {since} "
                "({n} item{s} across all chapters).".format(
                    since=since_iso[:10], n=n, s="" if n == 1 else "s"
                )
            )
        else:
            intro = (
                "All items in the knowledge store ({n} item{s}). "
                "No previous report found — this is the first run.".format(
                    n=n, s="" if n == 1 else "s"
                )
            )
    else:
        intro = (
            "Full running set for tags: {tags}.  {n} item{s} total.".format(
                tags=", ".join(ch.tags) if ch.tags else "-",
                n=n, s="" if n == 1 else "s",
            )
        )

    intro_p = doc.add_paragraph(intro)
    intro_p.paragraph_format.space_after = Pt(8)

    if not items:
        empty_p = doc.add_paragraph("No items available for this chapter.")
        empty_p.paragraph_format.left_indent = Inches(0.25)
        empty_p.paragraph_format.space_after  = Pt(12)
        er = empty_p.runs[0]
        er.font.italic     = True
        er.font.color.rgb  = RGBColor(0x80, 0x80, 0x80)
    else:
        for item in items:
            _add_item(doc, item)

    doc.add_paragraph()   # trailing spacer


# ── Unique report path ─────────────────────────────────────────────────────────


def _unique_report_path(reports_dir: Path) -> Path:
    """
    Return a path inside *reports_dir* that does not yet exist.

    Base name: biolitagent_digest_YYYYMMDD.docx
    On collision: biolitagent_digest_YYYYMMDD_001.docx, _002.docx, ...

    Previously generated reports are NEVER overwritten.
    """
    date_str = datetime.now().strftime("%Y%m%d")
    base = reports_dir / "biolitagent_digest_{}.docx".format(date_str)
    if not base.exists():
        return base
    for i in range(1, 1000):
        candidate = reports_dir / "biolitagent_digest_{}_{:03d}.docx".format(date_str, i)
        if not candidate.exists():
            return candidate
    raise RuntimeError(
        "Cannot find a unique report path for {} (tried 999 suffixes).".format(date_str)
    )


# ── Provenance & Footer Helpers ───────────────────────────────────────────────


def _get_provenance_info(conn: sqlite3.Connection) -> tuple[str, str, str]:
    """Retrieve (model_name, taxonomy_version, queries_version) for the report footer."""
    model_name = "gemini-2.5-flash"
    taxonomy_version = "1.1"
    queries_version = "1.1"

    # Try loading versions from config files
    tax_path = _ROOT / "config" / "chapter_taxonomy.json"
    if tax_path.exists():
        try:
            taxonomy_version = json.loads(tax_path.read_text(encoding="utf-8")).get("version", "1.1")
        except Exception:
            pass
    queries_path = _ROOT / "config" / "literature_queries.json"
    if queries_path.exists():
        try:
            queries_version = json.loads(queries_path.read_text(encoding="utf-8")).get("version", "1.1")
        except Exception:
            pass

    # Try finding model_name from knowledge_items metadata
    try:
        row = conn.execute("SELECT metadata_json FROM knowledge_items ORDER BY store_id DESC LIMIT 1").fetchone()
        if row and row[0]:
            meta = json.loads(row[0])
            model_name = meta.get("model_name") or meta.get("synthesis_model") or model_name
            cfgs = meta.get("config_versions", {})
            if isinstance(cfgs, dict):
                taxonomy_version = cfgs.get("taxonomy_version") or taxonomy_version
                queries_version = cfgs.get("queries_version") or queries_version
    except Exception:
        pass

    return model_name, taxonomy_version, queries_version


def _add_report_footer(
    doc:              "Document",
    generated_at:     str,
    model_name:       str,
    taxonomy_version: str,
    queries_version:  str,
) -> None:
    """Add a structured footer block and update section page footers."""
    # Update page footers across all document sections
    for section in doc.sections:
        footer = section.footer
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.text = (
            f"BioLitAgent Digest  |  Model: {model_name}  |  "
            f"Taxonomy: v{taxonomy_version}  |  Queries: v{queries_version}"
        )
        if p.runs:
            p.runs[0].font.name = "Calibri"
            p.runs[0].font.size = Pt(8.5)
            p.runs[0].font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)

    # Add a closing metadata footer block in document body
    doc.add_paragraph()  # spacer
    foot_p = doc.add_paragraph()
    foot_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = foot_p.add_run("―" * 44 + "\n")
    hr.font.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    r = foot_p.add_run(
        f"BioLitAgent Digest Provenance\n"
        f"Model: {model_name}   |   Taxonomy: v{taxonomy_version}   |   Queries: v{queries_version}\n"
        f"Generated: {generated_at[:19].replace('T', ' ')} UTC"
    )
    r.font.name = "Calibri"
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)


# ── Build report ───────────────────────────────────────────────────────────────


def build_report(
    conn:         sqlite3.Connection,
    since_iso:    Optional[str],
    report_path:  Path,
    generated_at: str,
    dry_run:      bool = False,
) -> None:
    """
    Generate the Word digest from *conn* and write it to *report_path*.

    READ-ONLY guarantee: no write operations are ever called on *conn*.
    NO OVERWRITE guarantee: *report_path* must not yet exist (caller's
    responsibility — use _unique_report_path()).

    Parameters
    ----------
    conn         : open read-only SQLite connection to knowledge_store.db
    since_iso    : cutoff timestamp for Chapter 1 (None = first run, all items)
    report_path  : destination .docx path (new file, must not exist)
    generated_at : ISO UTC timestamp for the cover page and last_report.json
    dry_run      : if True, log what would be generated without writing
    """
    total_items = read_total_count(conn)

    # Gather items for all chapters
    chapter_items: dict[int, list[dict[str, Any]]] = {}
    for ch in CHAPTERS:
        if ch.is_whats_new:
            chapter_items[ch.number] = read_items_since(conn, since_iso)
        else:
            chapter_items[ch.number] = read_items_by_tags(conn, ch.tags)

    chapter_counts = {n: len(v) for n, v in chapter_items.items()}

    # Dry-run: log and return without writing
    if dry_run:
        log.info("[DRY RUN] Would write: %s", report_path)
        log.info("[DRY RUN] Total items in knowledge store: %d", total_items)
        log.info("[DRY RUN] What's New cutoff: %s", since_iso or "(none - first run)")
        for ch in CHAPTERS:
            log.info(
                "[DRY RUN]   Chapter %d: %s -- %d item(s)",
                ch.number, ch.title, chapter_counts[ch.number],
            )
        return

    # Open template (preserves all styles); clear its body content
    log.info("Opening template: %s", _TEMPLATE_FILE.name)
    doc = Document(str(_TEMPLATE_FILE))
    _clear_document_body(doc)

    # Cover page
    _add_cover_page(doc, generated_at, since_iso, total_items, chapter_counts)

    # 8 content chapters
    for ch in CHAPTERS:
        n = chapter_counts[ch.number]
        log.info("  Chapter %d %-52s %3d item(s)", ch.number, ch.title, n)
        _add_chapter(doc, ch, chapter_items[ch.number], since_iso)

    # Add report footer (model name and config versions)
    model_name, tax_ver, queries_ver = _get_provenance_info(conn)
    _add_report_footer(doc, generated_at, model_name, tax_ver, queries_ver)

    # Save to a new file — template is never touched
    report_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(report_path))
    log.info("Report saved: %s", report_path)


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="report_generator",
        description=(
            "BioLitAgent Report Generator — reads the knowledge store and "
            "produces a timestamped Word digest."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        metavar="PATH",
        help="Path to knowledge_store.db (opened read-only).",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(_REPORTS_DIR),
        metavar="DIR",
        help="Directory to write the .docx report into.",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="ISO_TIMESTAMP",
        help=(
            "Override the 'What's New' cutoff timestamp.  "
            "Format: 2026-09-20T00:00:00+00:00.  "
            "Default: value from storage/last_report.json."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be generated without writing any files.",
    )
    parser.add_argument(
        "--list-chapters",
        action="store_true",
        help="Print the chapter structure and tag mapping, then exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── --list-chapters shortcut ─────────────────────────────────────────────
    if args.list_chapters:
        print("BioLitAgent report chapters and taxonomy tag mapping:")
        for ch in CHAPTERS:
            tags = ", ".join(ch.tags) if ch.tags else "(all items since last report)"
            print("  {n}. {title}".format(n=ch.number, title=ch.title))
            print("     Tags: {}".format(tags))
        return 0

    # ── Dependency check ─────────────────────────────────────────────────────
    if not _DOCX_AVAILABLE:
        log.error("python-docx is not installed.  Run:  pip install python-docx")
        return 1

    db_path     = Path(args.db)
    reports_dir = Path(args.reports_dir)

    # ── Resolve 'What's New' cutoff ──────────────────────────────────────────
    if args.since:
        since_iso = args.since
        log.info("What's New cutoff: %s  (from --since)", since_iso[:19])
    else:
        state     = load_last_report_state(_LAST_REPORT_FILE)
        since_iso = state.get("last_generated_at")
        if since_iso:
            log.info("What's New cutoff: %s  (from last_report.json)", since_iso[:19])
        else:
            log.info("What's New cutoff: (none)  -- first report, all items included")

    # ── Open DB read-only ────────────────────────────────────────────────────
    try:
        conn = open_db_readonly(db_path)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1

    total = read_total_count(conn)
    log.info("Knowledge store: %d approved item(s)", total)

    # ── Ensure template exists ───────────────────────────────────────────────
    create_template_if_missing()

    # ── Choose report path (never overwrites existing reports) ───────────────
    report_path  = _unique_report_path(reports_dir)
    generated_at = datetime.now(timezone.utc).isoformat()
    log.info("Report path: %s", report_path)

    # ── Generate report ──────────────────────────────────────────────────────
    try:
        build_report(
            conn         = conn,
            since_iso    = since_iso,
            report_path  = report_path,
            generated_at = generated_at,
            dry_run      = args.dry_run,
        )
    except Exception as exc:
        log.error("Report generation failed: %s", exc, exc_info=True)
        conn.close()
        return 1
    finally:
        conn.close()

    # ── Update last_report.json (only after a real, successful write) ────────
    if not args.dry_run:
        save_last_report_state(_LAST_REPORT_FILE, report_path, generated_at)
    else:
        log.info("[DRY RUN] Complete.  No files written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
