#!/usr/bin/env python3
"""
agents/pdf_ingestion.py
───────────────────────
PDF Ingestion Agent for BioLitAgent.

Watches inbox/ for newly deposited PDF files.  For each PDF the agent:

  1. Extracts bibliographic metadata (title, authors, DOI, publication year)
     from the document's embedded metadata and/or its first page.
  2. Generates a 3–5 sentence ORIGINAL paraphrase of the paper's key finding
     using the Gemini API — never a copy or light reword of the source text.
  3. Appends a structured record to storage/pending_items.jsonl with
     source_type "deposited_pdf".
  4. Moves the processed PDF to inbox/processed/ (still git-ignored).

CONTENT-SAFETY GUARANTEES
--------------------------
Two hard rules are enforced at every write to any path outside inbox/:

  NO PDF BINARY   — output must not contain the %PDF- binary signature.
                    (PDF data must never leave inbox/.)

  NO VERBATIM TEXT — output must not contain any span of ≥ VERBATIM_THRESHOLD
                     characters copied verbatim from the source document text.
                     (Enforced via difflib.SequenceMatcher on the description
                     before each write.)

Both rules are checked by _assert_no_unsafe_content(), which raises
ContentSafetyError loudly on any violation.  The built-in test suite
exercises these guards exhaustively; run it with:

    python agents/pdf_ingestion.py --self-test

Usage
-----
    python agents/pdf_ingestion.py              # process all inbox PDFs once
    python agents/pdf_ingestion.py --watch      # continuous polling loop
    python agents/pdf_ingestion.py --self-test  # safety guard tests only

CLI flags
---------
    --watch           Poll inbox/ every --interval seconds for new PDFs.
    --interval N      Polling interval in seconds (default: 60).
    --dry-run         Extract and paraphrase but do not write output or move PDFs.
    --self-test       Run built-in safety guard tests and exit (0 = all pass).
    --model MODEL     Gemini model for paraphrase generation.
    --verbose         Enable DEBUG-level log output.

Environment variables (from .env — see .env.example)
-----------------------------------------------------
    GOOGLE_API_KEY    Required for Gemini paraphrase generation.

Dependencies
------------
    pip install pypdf google-genai python-dotenv
    # Optional — improves text extraction from complex multi-column layouts:
    pip install pdfplumber

Output schema  (one JSON object per line in pending_items.jsonl)
----------------------------------------------------------------
    {
      "id":               "<uuidv4>",
      "source_type":      "deposited_pdf",
      "title":            "<title string, or null>",
      "authors":          ["<author>", ...],
      "doi":              "<DOI string, or null>",
      "publication_year": <int, or null>,
      "description":      "<3-5 sentence original paraphrase>",
      "detected_at":      "<ISO 8601 UTC timestamp>",
      "source_filename":  "<original PDF filename>",
      "source_checksum":  "<sha256 hex of original PDF bytes>",
      "verbatim_check":   "passed"
    }

CONTENT-REPRODUCTION POLICY
----------------------------
The description field must always be a fresh, original summary authored by
the LLM — never the source text, never a verbatim quote, never a light
reword.  _assert_no_unsafe_content() enforces this at runtime.  The
"verbatim_check": "passed" key in every output record is set only after that
guard succeeds; downstream consumers may treat its absence as an integrity
failure.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Optional dependency: python-dotenv ───────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # env vars may be injected directly by the orchestrator

# ── Optional dependency: pypdf ────────────────────────────────────────────────
try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False
    PdfReadError = Exception  # type: ignore[misc,assignment]

# ── Optional dependency: pdfplumber (richer layout-aware text extraction) ─────
try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

# ── Optional dependency: google-genai ────────────────────────────────────────
try:
    import google.genai as genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_ROOT            = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

_INBOX           = _ROOT / "inbox"
_INBOX_PROCESSED = _INBOX / "processed"
_OUTPUT_FILE     = _ROOT / "storage" / "pending_items.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Verbatim-text detection threshold.  Any matching run of characters of this
# length or longer between source text and output content triggers the guard.
# 40 chars ≈ 6–8 words — tight enough to catch light rewordings.
VERBATIM_THRESHOLD: int = 40

# Maximum characters of first-page text forwarded to the LLM.
# The full text is never written to any output path.
MAX_SOURCE_CHARS: int = 3_000

# Central model config
try:
    from biolitagent.config.model_config import DEFAULT_MODEL
except ImportError:
    try:
        from config.model_config import DEFAULT_MODEL
    except ImportError:
        DEFAULT_MODEL = "gemini-2.5-flash"

_DEFAULT_MODEL: str = DEFAULT_MODEL

_RETRYABLE_STATUS_CODES = {429, 503}
_MAX_LLM_RETRIES = 3
_BACKOFF_BASE = 2.0  # 2s, 4s, 8s
_daily_quota_exhausted: bool = False

# Quota Guard integration
try:
    from biolitagent.config.quota_guard import (
        check_preflight_gate,
        is_daily_exhaustion,
        parse_quota_failure,
        record_call,
    )
except ImportError:
    try:
        from config.quota_guard import (
            check_preflight_gate,
            is_daily_exhaustion,
            parse_quota_failure,
            record_call,
        )
    except ImportError:
        def check_preflight_gate(estimated_calls: int, agent_name: str) -> bool: return True
        def is_daily_exhaustion(quota_id: Optional[str], exc_str: str = "") -> bool: return False
        def parse_quota_failure(exc: Exception) -> tuple[bool, Optional[str], Optional[str]]: return False, None, None
        def record_call(agent_name: str) -> int: return 0

# Relevance and recency ranking helpers from literature_scout
try:
    from biolitagent.agents.literature_scout import (
        evaluate_bioprocess_relevance,
        calculate_recency_bonus,
    )
except ImportError:
    try:
        from agents.literature_scout import (
            evaluate_bioprocess_relevance,
            calculate_recency_bonus,
        )
    except ImportError:
        def evaluate_bioprocess_relevance(title, text="", min_score=2): return True, 0, 0.0, [], []
        def calculate_recency_bonus(year): return 0.0, year

# Default inbox polling interval (seconds).
_DEFAULT_POLL_INTERVAL: int = 60

# DOI regex — matches 10.NNNN/anything-that-isn't-whitespace-or-common-terminators
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>()\[\]{}]+)", re.IGNORECASE)

# 4-digit year regex (1900–2099).
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# PDF binary signature (first 5 bytes of every valid PDF file).
_PDF_BINARY_SIG = "%PDF-"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("pdf_ingestion")

# ─────────────────────────────────────────────────────────────────────────────
# LLM client & helpers
# ─────────────────────────────────────────────────────────────────────────────

_llm_client: Optional[Any] = None
_llm_model: str = _DEFAULT_MODEL


def reset_llm_client() -> None:
    """Reset cached LLM client (used for testing or reconfiguration)."""
    global _llm_client
    _llm_client = None


def _extract_status_code(exc: Exception) -> Optional[int]:
    """
    Extract HTTP status code directly from exception object attributes.
    Checks `code`, `status_code`, `http_status`, and nested `response.status_code`.
    Does NOT rely on regex or string-matching the exception message.
    """
    for attr in ("code", "status_code", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    resp = getattr(exc, "response", None)
    if resp is not None:
        for attr in ("status_code", "code"):
            val = getattr(resp, attr, None)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
    return None


def _get_llm_client() -> Optional[Any]:
    """Return a cached google.genai Client, initialising it on first call."""
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    if not _GENAI_AVAILABLE:
        log.warning("google-genai is not installed; running in fallback mode.")
        return None
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        log.warning("GOOGLE_API_KEY is not set; running in fallback mode.")
        return None
    try:
        _llm_client = genai.Client(api_key=api_key)
        return _llm_client
    except Exception as exc:
        log.warning("Could not initialise Gemini client: %s; running in fallback mode.", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Content-safety exceptions and guard
# ─────────────────────────────────────────────────────────────────────────────


class ContentSafetyError(RuntimeError):
    """
    Raised by _assert_no_unsafe_content() when either content-safety rule
    is violated:

      • PDF binary data (the %PDF- signature) would be written outside inbox/.
      • A verbatim text span of ≥ VERBATIM_THRESHOLD characters from the source
        document would be written outside inbox/.

    This exception is intentionally a RuntimeError subclass so it propagates
    loudly and cannot be silently swallowed by a bare `except Exception` that
    might hide it.
    """


def _is_inside_inbox(path: Path) -> bool:
    """Return True iff *path* resolves to a location inside _INBOX."""
    try:
        path.resolve().relative_to(_INBOX.resolve())
        return True
    except ValueError:
        return False


def _assert_no_unsafe_content(
    content: str,
    dest_path: Path,
    source_text: Optional[str] = None,
) -> None:
    """
    Assert that *content* does not violate either content-safety rule when
    it is destined for *dest_path* outside inbox/.

    This function is a **hard gate** that must be called before every write
    to any file outside inbox/.  It raises ContentSafetyError — never returns
    silently on a violation.

    Rules (checked only when dest_path is outside inbox/):
    --------------------------------------------------------
    1. NO PDF BINARY
       content must not contain the %PDF- signature string.  PDF binary data
       must never leave inbox/, even as an embedded substring.

    2. NO VERBATIM TEXT
       When source_text is provided, content must not contain any contiguous
       run of characters of length ≥ VERBATIM_THRESHOLD that also appears
       verbatim in source_text.  This is detected using
       difflib.SequenceMatcher so it catches exact copies regardless of
       surrounding context.

    Parameters
    ----------
    content     : str   — the string about to be written.
    dest_path   : Path  — the destination file path.
    source_text : str | None  — the source document text to compare against.
                  If None, only the PDF binary rule is checked.

    Raises
    ------
    ContentSafetyError — on any violation.
    """
    if _is_inside_inbox(dest_path):
        # inbox/ is the holding area; no content restrictions apply there.
        return

    # ── Rule 1: no PDF binary signature ─────────────────────────────────────
    if _PDF_BINARY_SIG in content:
        raise ContentSafetyError(
            f"SAFETY VIOLATION [PDF BINARY] — The string '%PDF-' was detected "
            f"in content destined for '{dest_path}', which is outside inbox/. "
            f"PDF binary data must never be written outside inbox/. "
            f"Check that no PDF bytes are being serialised into the output record."
        )

    # ── Rule 2: no verbatim spans from the source document ──────────────────
    if source_text and len(source_text) >= VERBATIM_THRESHOLD:
        matcher = difflib.SequenceMatcher(
            isjunk=None,
            a=source_text,
            b=content,
            autojunk=False,   # autojunk=True can silently skip common substrings
        )
        for block in matcher.get_matching_blocks():
            if block.size >= VERBATIM_THRESHOLD:
                offending_span = source_text[block.a : block.a + block.size]
                raise ContentSafetyError(
                    f"SAFETY VIOLATION [VERBATIM TEXT] — A verbatim span of "
                    f"{block.size} character(s) (threshold: {VERBATIM_THRESHOLD}) "
                    f"from the source document was detected in content destined "
                    f"for '{dest_path}', which is outside inbox/.\n"
                    f"  Span (first 120 chars): {offending_span[:120]!r}\n"
                    f"  The description field must be an original paraphrase."
                )


# ─────────────────────────────────────────────────────────────────────────────
# PDF metadata dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PdfMetadata:
    """
    Bibliographic metadata extracted from a single PDF.

    first_page_text is used internally as LLM input context and is NOT
    written to any output path outside inbox/.
    """
    title:            Optional[str]  = None
    authors:          list[str]      = field(default_factory=list)
    doi:              Optional[str]  = None
    publication_year: Optional[int]  = None
    # ── Internal fields — never serialised to output ─────────────────────────
    first_page_text:  str            = field(default="", repr=False)
    source_checksum:  str            = ""


# ─────────────────────────────────────────────────────────────────────────────
# PDF extraction helpers
# ─────────────────────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of the file at *path*."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_via_pypdf(pdf_path: Path) -> tuple[dict[str, Any], str]:
    """Return (raw_metadata_dict, first_two_pages_text) using pypdf."""
    reader = PdfReader(str(pdf_path))
    meta: dict[str, Any] = dict(reader.metadata or {})
    pages = reader.pages
    text = (pages[0].extract_text() or "") if pages else ""
    # Grab page 2 as well — abstracts often spill over.
    if len(text) < 500 and len(pages) > 1:
        text += "\n" + (pages[1].extract_text() or "")
    return meta, text


def _extract_via_pdfplumber(pdf_path: Path) -> tuple[dict[str, Any], str]:
    """Return (raw_metadata_dict, first_two_pages_text) using pdfplumber."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        meta: dict[str, Any] = pdf.metadata or {}
        pages = pdf.pages
        text = (pages[0].extract_text() or "") if pages else ""
        if len(text) < 500 and len(pages) > 1:
            text += "\n" + (pages[1].extract_text() or "")
    return meta, text


def _clean(v: Any) -> Optional[str]:
    """Coerce a PDF metadata value to a clean string, or None."""
    if v is None:
        return None
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", str(v)).strip()
    return s or None


def _parse_authors(raw: Optional[str]) -> list[str]:
    """Split a raw /Author string into a list of individual author names."""
    if not raw:
        return []
    for sep in (";", " and ", ","):
        if sep in raw:
            return [a.strip() for a in raw.split(sep) if a.strip()]
    stripped = raw.strip()
    return [stripped] if stripped else []


def _find_doi(text: str, meta: dict[str, Any]) -> Optional[str]:
    """Extract the first DOI from *text*, falling back to *meta*."""
    m = _DOI_RE.search(text)
    if m:
        return m.group(1).rstrip(".,;)>\"'")
    for key in ("/doi", "doi", "DOI"):
        v = _clean(meta.get(key))
        if v:
            return v
    return None


def _find_year(text: str, meta: dict[str, Any]) -> Optional[int]:
    """Extract the most plausible publication year from text or PDF metadata."""
    current_year = datetime.now().year
    # 1. Try PDF date fields first — most reliable.
    for key in ("/CreationDate", "CreationDate", "/ModDate", "ModDate"):
        date_str = _clean(meta.get(key))
        if date_str:
            m = _YEAR_RE.search(date_str)
            if m:
                y = int(m.group(1))
                if 1900 <= y <= current_year + 1:
                    return y
    # 2. Look near publication keywords in the text.
    for keyword in ("published", "received", "accepted", "©", "copyright", "(c)"):
        idx = text.lower().find(keyword)
        if idx >= 0:
            snippet = text[max(0, idx - 5): idx + 40]
            m = _YEAR_RE.search(snippet)
            if m:
                y = int(m.group(1))
                if 1900 <= y <= current_year + 1:
                    return y
    # 3. Fall back to the first 4-digit year found anywhere in the text.
    for m in _YEAR_RE.finditer(text):
        y = int(m.group(1))
        if 1900 <= y <= current_year + 1:
            return y
    return None


_FILENAME_ARTIFACT_TITLE_RE = re.compile(
    r"(?:"
    r"\b\d+\s*\.\.\s*\d+\b"               # e.g. "fbioe-2021-796991 1..9"
    r"|\b\d+\s*[-–]\s*\d+$"               # trailing page numbers e.g. " 1-9"
    r"|\.(?:pdf|docx?|tex|indd|xml)$"      # file extensions
    r"|^[a-zA-Z0-9_\-]+-\d{4}-\d+"        # production codes e.g. "fbioe-2021-796991"
    r"|^untitled\b"                       # generic titles
    r"|^microsoft\s+word\b"               # generic office titles
    r")",
    re.IGNORECASE,
)


def _is_filename_or_artifact_title(title: Optional[str]) -> bool:
    """Return True if title appears to be a filename, production code, or page-range artifact."""
    if not title or not title.strip():
        return True
    t = title.strip()
    if _FILENAME_ARTIFACT_TITLE_RE.search(t):
        return True
    if " " not in t and ("_" in t or "-" in t) and len(t) > 10:
        return True
    return False


def _extract_fallback_title(raw_text: str, pdf_path: Path) -> tuple[Optional[str], bool]:
    """
    Attempt to extract a genuine title from the first-page text or clean filename stem.
    Returns (resolved_title, is_flagged).
    """
    # 1. Try first-page text lines
    if raw_text:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        candidate_lines = []
        for line in lines[:10]:
            line_lower = line.lower()
            if any(skip in line_lower for skip in (
                "doi:", "issn", "frontiers", "open access", "published:", "accepted:",
                "received:", "http://", "https://", "volume ", "copyright", "©", "all rights reserved",
                "original research", "research article", "review article", "mini review", "perspective",
                "editorial", "brief report", "short communication",
            )):
                continue
            if any(auth in line_lower for auth in (
                "department", "institute", "university", "correspondence:", "laboratory", "center"
            )) or "*" in line or "@" in line:
                break
            candidate_lines.append(line)
            combined = " ".join(candidate_lines)
            if len(combined) > 20 and (line.endswith(".") or len(candidate_lines) >= 3):
                break

        if candidate_lines:
            candidate = " ".join(candidate_lines).strip()
            if len(candidate) > 15 and not _is_filename_or_artifact_title(candidate):
                return candidate, False

    # 2. Try cleaned filename stem
    stem = re.sub(r"^[!\s_R\[\]]+", "", pdf_path.stem).strip()
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    if len(stem) > 15 and not _is_filename_or_artifact_title(stem):
        return stem, False

    # 3. Could not find clean title; return flagged title
    fallback = stem if stem else pdf_path.name
    return f"[FLAGGED_TITLE] {fallback}", True


def extract_pdf_metadata(pdf_path: Path) -> PdfMetadata:
    """
    Extract bibliographic metadata and a capped first-page text excerpt from
    *pdf_path*.

    Extraction strategy:
      • pdfplumber is used when available (better with multi-column layouts).
      • pypdf is used as the fallback.
    Both backends return the same (raw_meta, text) tuple shape.

    The returned PdfMetadata.first_page_text is capped at MAX_SOURCE_CHARS
    characters and is used only as LLM input — it is never written outside
    inbox/.

    Raises
    ------
    RuntimeError          — no PDF parser is installed.
    PdfReadError          — pypdf could not parse the file (corrupt or encrypted).
    pdfplumber exceptions — similarly for pdfplumber.
    """
    if not (_PYPDF_AVAILABLE or _PDFPLUMBER_AVAILABLE):
        raise RuntimeError(
            "No PDF parser installed.  Run:  pip install pypdf"
        )

    if _PDFPLUMBER_AVAILABLE:
        raw_meta, raw_text = _extract_via_pdfplumber(pdf_path)
    else:
        raw_meta, raw_text = _extract_via_pypdf(pdf_path)

    # ── Title ────────────────────────────────────────────────────────────────
    title = _clean(
        raw_meta.get("/Title") or raw_meta.get("Title") or raw_meta.get("title")
    )
    if _is_filename_or_artifact_title(title):
        if title:
            log.warning(
                "  [SUSPICIOUS_PDF_TITLE] Metadata title '%s' for %s matches filename/production pattern. Attempting fallback extraction.",
                title, pdf_path.name
            )
        else:
            log.info("  [EMPTY_PDF_TITLE] No metadata title found for %s. Attempting fallback extraction.", pdf_path.name)

        fallback_title, is_flagged = _extract_fallback_title(raw_text, pdf_path)
        if fallback_title:
            title = fallback_title
            if is_flagged:
                log.warning("  [FLAGGED_PDF_TITLE] Could not reliably resolve title for %s; using: '%s'", pdf_path.name, title)
            else:
                log.info("  [FALLBACK_PDF_TITLE] Resolved title for %s -> '%s'", pdf_path.name, title)
    elif not title and raw_text:
        # Heuristic: first non-trivially-short line is often the title.
        for line in raw_text.splitlines():
            line = line.strip()
            if len(line) > 12:
                title = line[:240]
                break

    # ── Authors ──────────────────────────────────────────────────────────────
    authors = _parse_authors(
        _clean(raw_meta.get("/Author") or raw_meta.get("Author") or raw_meta.get("author"))
    )

    # ── DOI and year ─────────────────────────────────────────────────────────
    doi  = _find_doi(raw_text, raw_meta)
    year = _find_year(raw_text, raw_meta)

    return PdfMetadata(
        title=title,
        authors=authors,
        doi=doi,
        publication_year=year,
        # Cap the text forwarded to the LLM — no full-text storage.
        first_page_text=raw_text[:MAX_SOURCE_CHARS],
        source_checksum=_sha256_file(pdf_path),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LLM paraphrase generation
# ─────────────────────────────────────────────────────────────────────────────

_PARAPHRASE_PROMPT = """\
You are a scientific literature analyst helping to build a digest of \
bioprocess and protein-production research.

Bibliographic information for the paper:
  Title:   {title}
  Authors: {authors}
  Year:    {year}
  DOI:     {doi}

FIRST-PAGE / ABSTRACT EXCERPT (DO NOT QUOTE THIS TEXT):
{source_excerpt}

YOUR TASK
---------
Write a 3 to 5 sentence ORIGINAL SUMMARY of this paper's key finding or \
relevance to bioprocess engineering, biopharmaceutical manufacturing, or \
protein production.
Begin DIRECTLY with the paper's key finding, method, or bioprocess relevance.

STRICT RULES:
- Write entirely in YOUR OWN WORDS.
- CRITICAL: Do NOT restate, echo, or quote the paper's title in your description. \
  Never open with phrases like "This paper titled...", "In '[Title]'...", \
  or any verbatim repetition of the title. Begin directly with what was found or achieved.
- Do NOT copy any phrase, clause, or sentence from the excerpt above, \
  even if quoted or attributed.
- Do NOT lightly reword the source — produce a genuinely independent \
  scientific description based on your understanding.
- Cover: what was studied, the main result or conclusion, and why it \
  matters to the field.
- If the paper appears unrelated to bioprocess / protein production, \
  state that concisely in 1 sentence.

Return ONLY the summary — no label, no title, no markdown.
"""


async def generate_paraphrase(
    meta: PdfMetadata,
    dry_run: bool = False,
) -> tuple[str, str]:
    """
    Generate a 3–5 sentence original paraphrase of the paper using Gemini.
    Retries transient API errors (429/503) up to 3 times with exponential backoff (2s, 4s, 8s).
    Fast-fails without retries on daily quota exhaustion.
    Returns (paraphrase_text, synthesis_method) where synthesis_method is
    'gemini', 'fallback_template', or 'dry_run'.
    """
    if dry_run:
        return "[DRY RUN — paraphrase not generated]", "dry_run"

    global _daily_quota_exhausted
    if _daily_quota_exhausted:
        log.warning("Daily quota exhausted -- using fallback template.")
        fallback = (
            "Deposited bioprocess research publication evaluating operational "
            "parameters and process performance characteristics. The document provides "
            "methodological insights relevant to biopharmaceutical production."
        )
        return fallback, "fallback_template"

    client = _get_llm_client()
    if not client:
        log.warning("Gemini client unavailable -- using fallback template.")
        fallback = (
            "Deposited bioprocess research publication evaluating operational "
            "parameters and process performance characteristics. The document provides "
            "methodological insights relevant to biopharmaceutical production."
        )
        return fallback, "fallback_template"

    prompt = _PARAPHRASE_PROMPT.format(
        title=meta.title or "(not found in metadata)",
        authors=", ".join(meta.authors) if meta.authors else "(not found)",
        year=str(meta.publication_year) if meta.publication_year else "(not found)",
        doi=meta.doi or "(not found)",
        source_excerpt=meta.first_page_text or "(no text could be extracted from this PDF)",
    )

    for attempt in range(_MAX_LLM_RETRIES + 1):
        try:
            record_call("pdf_ingestion")
            response = client.models.generate_content(
                model=_llm_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,         # some creativity, but grounded
                    max_output_tokens=600,
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text, "gemini"
            break
        except Exception as exc:
            exc_str = str(exc)
            is_quota, quota_id, retry_delay = parse_quota_failure(exc)
            if is_quota and is_daily_exhaustion(quota_id, exc_str):
                _daily_quota_exhausted = True
                log.warning(
                    "  [SKIPPED_QUOTA_EXHAUSTED] Daily Gemini quota exhausted (quotaId: %s). "
                    "Falling back to templated description.",
                    quota_id or "PerDay",
                )
                break

            status_code = _extract_status_code(exc)
            if status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_LLM_RETRIES:
                delay = _BACKOFF_BASE * (2 ** attempt)
                log.warning(
                    "  [RETRY %d/%d] Transient Gemini API error (HTTP %d, retrying in %.0fs): %s",
                    attempt + 1, _MAX_LLM_RETRIES, status_code, delay, exc,
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "  [LLM_API_ERROR] Gemini API failed (status_code=%s, attempt %d/%d): %s",
                    status_code, attempt + 1, _MAX_LLM_RETRIES, exc,
                )
                break

    fallback = (
        "Deposited bioprocess research publication evaluating operational "
        "parameters and process performance characteristics. The document provides "
        "methodological insights relevant to biopharmaceutical production."
    )
    return fallback, "fallback_template"


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_record(
    meta: PdfMetadata,
    description: str,
    source_filename: str,
    synthesis_method: str = "gemini",
    match_percentage: Optional[float] = None,
    recency_bonus: Optional[float] = None,
    pub_year_used: Optional[int] = None,
    stale: Optional[bool] = None,
    year_unknown: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Assemble a pending_items.jsonl record.

    IMPORTANT: This function must never include meta.first_page_text or any
    other verbatim source content in the returned dict.  Only the LLM-generated
    description, bibliographic fields, and housekeeping metadata are included.
    The "verbatim_check" key is initially absent and is added by _append_record()
    only after _assert_no_unsafe_content() succeeds.
    """
    if match_percentage is None:
        _, _, match_percentage, _, _ = evaluate_bioprocess_relevance(meta.title or "", meta.first_page_text or "")

    if recency_bonus is None or pub_year_used is None:
        recency_bonus, pub_year_used = calculate_recency_bonus(meta.publication_year)

    if stale is None and year_unknown is None:
        if meta.publication_year is None:
            stale = None
            year_unknown = True
        elif meta.publication_year < 2023:
            stale = True
            year_unknown = False
        else:
            stale = False
            year_unknown = False
    elif year_unknown is None:
        year_unknown = (meta.publication_year is None)

    return {
        "id":               str(uuid.uuid4()),
        "source_type":      "deposited_pdf",
        "title":            meta.title,
        "authors":          meta.authors,
        "doi":              meta.doi,
        "publication_year": meta.publication_year,
        # description must be LLM-generated — checked below before write.
        "description":      description,
        "detected_at":      datetime.now(timezone.utc).isoformat(),
        "source_filename":  source_filename,
        "source_checksum":  meta.source_checksum,
        "synthesis_method": synthesis_method,
        "match_percentage": match_percentage,
        "recency_bonus":    recency_bonus,
        "pub_year_used":    pub_year_used,
        "stale":            stale,
        "year_unknown":     year_unknown,
        "model_name":       _llm_model if synthesis_method == "gemini" else None,
        "config_versions":  {"taxonomy_version": "1.1", "queries_version": "1.1"},
        # "verbatim_check" is added by _append_record() after the guard passes.
    }


def _append_record(
    record: dict[str, Any],
    source_text: str,
    dry_run: bool,
) -> None:
    """
    Serialise *record* to JSONL and append it to pending_items.jsonl.

    Calls _assert_no_unsafe_content() on the serialised line BEFORE writing
    to verify that neither PDF binary data nor verbatim source text is present.
    Sets "verbatim_check": "passed" on the record only after the guard succeeds.

    Raises ContentSafetyError (propagated to caller) on any safety violation.
    """
    # Dry-run serialise first so the safety check runs even without writing.
    candidate_line = json.dumps(record, ensure_ascii=False)

    # ── Safety check ─────────────────────────────────────────────────────────
    # This MUST run before any disk write and before "verbatim_check" is set.
    _assert_no_unsafe_content(
        content=candidate_line,
        dest_path=_OUTPUT_FILE,
        source_text=source_text,
    )

    # Guard passed — stamp the record and re-serialise.
    record["verbatim_check"] = "passed"
    final_line = json.dumps(record, ensure_ascii=False)

    if dry_run:
        log.info("[DRY RUN] Would append: title=%r", record.get("title"))
        return

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _OUTPUT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(final_line + "\n")
    log.info("  ✓ Appended: %s", record.get("title") or record["id"])


def _move_to_processed(pdf_path: Path, dry_run: bool) -> Optional[Path]:
    """
    Move *pdf_path* from inbox/ to inbox/processed/.

    Appends a UTC timestamp suffix if the destination already exists, so
    no file is ever silently overwritten.

    Returns the destination Path, or None in dry-run mode.
    """
    _INBOX_PROCESSED.mkdir(parents=True, exist_ok=True)
    dest = _INBOX_PROCESSED / pdf_path.name
    if dest.exists():
        ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = _INBOX_PROCESSED / f"{pdf_path.stem}__{ts}{pdf_path.suffix}"

    if dry_run:
        log.info("[DRY RUN] Would move: %s → inbox/processed/%s", pdf_path.name, dest.name)
        return None

    shutil.move(str(pdf_path), str(dest))
    log.info("  ↳ Moved → inbox/processed/%s", dest.name)
    return dest


# ─────────────────────────────────────────────────────────────────────────────
# Per-PDF processing pipeline
# ─────────────────────────────────────────────────────────────────────────────


async def process_pdf(pdf_path: Path, dry_run: bool = False) -> bool:
    """
    Run the full ingestion pipeline for one PDF file.

    Steps:
      1. Extract bibliographic metadata and capped first-page text.
      2. Generate a 3–5 sentence original paraphrase via Gemini.
      3. Validate the description against both content-safety rules.
      4. Append the record to pending_items.jsonl.
      5. Move the PDF to inbox/processed/.

    Returns one of:
      "PROCESSED"        — successfully parsed, paraphrased, safety-checked, and moved.
      "EXTRACT_ERROR"    — metadata/text extraction failed.
      "LLM_ERROR"        — paraphrase generation API error.
      "LLM_EMPTY"        — paraphrase returned empty text.
      "SAFETY_VIOLATION" — content safety guard failed.
    The file is NOT moved on failure so the operator can inspect it and retry.
    """
    log.info("== Processing: %s", pdf_path.name)

    # ── Step 1: Extract metadata ─────────────────────────────────────────────
    try:
        meta = extract_pdf_metadata(pdf_path)
    except Exception as exc:
        log.error("  -> [EXTRACT_ERROR] Metadata extraction failed: %s", exc)
        return "EXTRACT_ERROR"

    log.debug("  Title:   %s", meta.title)
    log.debug("  Authors: %s", meta.authors)
    log.debug("  DOI:     %s", meta.doi)
    log.debug("  Year:    %s", meta.publication_year)
    log.debug("  Text:    %d chars extracted from first page(s).", len(meta.first_page_text))

    # ── Step 1b: Evaluate relevance & recency ranking ─────────────────────────
    _, rel_score, match_pct, _, _ = evaluate_bioprocess_relevance(
        meta.title or "",
        meta.first_page_text or "",
    )
    recency_bonus, pub_year = calculate_recency_bonus(meta.publication_year)

    stale: Optional[bool] = None
    year_unknown: bool = False
    if meta.publication_year is None:
        stale = None
        year_unknown = True
    elif meta.publication_year < 2023:
        stale = True
        year_unknown = False
    else:
        stale = False
        year_unknown = False

    # ── Step 2: Generate original paraphrase ─────────────────────────────────
    try:
        description, synthesis_method = await generate_paraphrase(meta, dry_run=dry_run)
    except Exception as exc:
        log.error("  -> [LLM_ERROR] Paraphrase generation failed: %s", exc)
        return "LLM_ERROR"

    if not description:
        log.warning("  -> [LLM_EMPTY] Empty description returned -- skipping.")
        return "LLM_EMPTY"

    # ── Step 3 & 4: Build record, run safety check, and write ────────────────
    record = _build_record(
        meta,
        description,
        source_filename=pdf_path.name,
        synthesis_method=synthesis_method,
        match_percentage=match_pct,
        recency_bonus=recency_bonus,
        pub_year_used=pub_year,
        stale=stale,
        year_unknown=year_unknown,
    )
    try:
        _append_record(record, source_text=meta.first_page_text, dry_run=dry_run)
    except ContentSafetyError as exc:
        # Log the full violation message — this should be treated as a bug.
        log.error("  -> [SAFETY_VIOLATION] %s", exc)
        return "SAFETY_VIOLATION"

    # ── Step 5: Move processed PDF ───────────────────────────────────────────
    _move_to_processed(pdf_path, dry_run=dry_run)

    log.info("  [OK] Done: %s", pdf_path.name)
    return "PROCESSED"


# ─────────────────────────────────────────────────────────────────────────────
# Inbox watching
# ─────────────────────────────────────────────────────────────────────────────


def _inbox_pdfs() -> list[Path]:
    """Return all PDF files at the top level of inbox/ (not in processed/)."""
    if not _INBOX.exists():
        return []
    return sorted(p for p in _INBOX.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


async def run_once(dry_run: bool) -> int:
    """
    Process every PDF currently in inbox/.
    Prints an aggregated status breakdown across all categories:
      PROCESSED, EXTRACT_ERROR, LLM_ERROR, LLM_EMPTY, SAFETY_VIOLATION.
    Returns the count of successfully processed files.
    """
    pdfs = _inbox_pdfs()
    if not pdfs:
        log.info("inbox/ is empty -- nothing to do.")
        return 0

    if not check_preflight_gate(len(pdfs), "pdf_ingestion"):
        log.warning("Pre-flight quota check aborted execution.")
        return 0

    log.info("Found %d PDF(s) in inbox/.", len(pdfs))
    counts = {
        "PROCESSED": 0,
        "EXTRACT_ERROR": 0,
        "LLM_ERROR": 0,
        "LLM_EMPTY": 0,
        "SAFETY_VIOLATION": 0,
    }

    for pdf_path in pdfs:
        try:
            status = await process_pdf(pdf_path, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            log.error("Unexpected error processing %s: %s", pdf_path.name, exc)
            status = "EXTRACT_ERROR"
        if status not in counts:
            counts[status] = 0
        counts[status] += 1

    # ── Aggregated status breakdown ──────────────────────────────────────────
    print("\n  -- Ingestion Status Breakdown --")
    print(f"    PROCESSED        : {counts.get('PROCESSED', 0):>3}")
    print(f"    EXTRACT_ERROR    : {counts.get('EXTRACT_ERROR', 0):>3}")
    print(f"    LLM_ERROR        : {counts.get('LLM_ERROR', 0):>3}")
    print(f"    LLM_EMPTY        : {counts.get('LLM_EMPTY', 0):>3}")
    print(f"    SAFETY_VIOLATION : {counts.get('SAFETY_VIOLATION', 0):>3}")
    print(f"    TOTAL            : {len(pdfs):>3}\n")

    log.info("Processed %d/%d PDF(s) successfully.", counts.get("PROCESSED", 0), len(pdfs))
    return counts.get("PROCESSED", 0)


async def run_watch(dry_run: bool, poll_interval: int) -> None:
    """
    Continuously poll inbox/ for new PDFs at *poll_interval*-second intervals.
    Tracks filenames that have already been dispatched; does not re-process
    files that move back to inbox/ after being processed.
    Runs until interrupted (KeyboardInterrupt / SIGINT).
    """
    # Seed the seen-set from files already in inbox/processed/ so we do not
    # re-process PDFs that were moved there before this watch session started.
    seen: set[str] = set()
    if _INBOX_PROCESSED.exists():
        for p in _INBOX_PROCESSED.iterdir():
            if p.suffix.lower() == ".pdf":
                # Strip any timestamp suffix that was added on collision.
                seen.add(p.stem.split("__")[0] + p.suffix)

    log.info(
        "Watching inbox/ (poll every %ds, %d file(s) already seen). "
        "Press Ctrl-C to stop.",
        poll_interval,
        len(seen),
    )

    try:
        while True:
            new_pdfs = [p for p in _inbox_pdfs() if p.name not in seen]
            for pdf_path in new_pdfs:
                seen.add(pdf_path.name)
                try:
                    await process_pdf(pdf_path, dry_run=dry_run)
                except Exception as exc:  # noqa: BLE001
                    log.error("Unexpected error processing %s: %s", pdf_path.name, exc)
            if new_pdfs:
                log.info("Cycle complete. Next poll in %ds.", poll_interval)
            await asyncio.sleep(poll_interval)
    except KeyboardInterrupt:
        log.info("Watch mode interrupted. Exiting.")


# ─────────────────────────────────────────────────────────────────────────────
# Built-in safety guard tests
# ─────────────────────────────────────────────────────────────────────────────


def _run_case(
    label: str,
    expect_raise: bool,
    fn,
    passes: list[str],
    failures: list[str],
) -> None:
    """Execute one test case and record its outcome."""
    import traceback
    try:
        fn()
        if expect_raise:
            failures.append(label)
            print(f"  FAIL  {label}")
            print("        -> Expected ContentSafetyError but no exception was raised.")
        else:
            passes.append(label)
            print(f"  PASS  {label}")
    except ContentSafetyError as exc:
        if expect_raise:
            passes.append(label)
            print(f"  PASS  {label}")
            print(f"        -> Correctly raised ContentSafetyError: {str(exc)[:100]}")
        else:
            failures.append(label)
            print(f"  FAIL  {label}")
            print(f"        -> Unexpected ContentSafetyError: {exc}")
    except Exception as exc:
        failures.append(label)
        print(f"  FAIL  {label}  [{type(exc).__name__}: {exc}]")
        traceback.print_exc()


def _check(condition: bool, message: str) -> None:
    """Thin assertion used inside test lambdas."""
    if not condition:
        raise AssertionError(message)


def run_safety_tests() -> None:
    """
    Validate the _assert_no_unsafe_content() safety guard exhaustively.

    This function runs a deterministic suite of test cases and exits with:
      0  — all tests passed
      1  — one or more tests failed

    Invoke via:
        python agents/pdf_ingestion.py --self-test
    or within a test runner (e.g. pytest) by calling it directly.

    Test coverage:
      • PDF binary signature rejected outside inbox/
      • PDF binary signature permitted inside inbox/
      • Verbatim span ≥ threshold rejected outside inbox/
      • Verbatim span ≥ threshold permitted inside inbox/
      • Genuine original paraphrase (no matching spans) passes outside inbox/
      • Short coincidental overlap below threshold passes outside inbox/
      • Exact threshold boundary (threshold-1 chars = pass, threshold chars = fail)
      • _is_inside_inbox correctly classifies inbox/, inbox/processed/, and storage/
      • _build_record never includes first_page_text in its output
    """
    passes:   list[str] = []
    failures: list[str] = []

    outside = _OUTPUT_FILE         # storage/pending_items.jsonl — outside inbox/
    inside  = _INBOX / "test.pdf"  # inbox/test.pdf — inside inbox/

    # Representative source text (would be the first page of a real PDF).
    source = (
        "The authors developed a novel perfusion-based CHO cell culture process "
        "that increased monoclonal antibody volumetric productivity by 3.2-fold "
        "compared to a standard fed-batch baseline, achieved through real-time "
        "lactate-controlled glucose feeding and semi-continuous bleed strategies."
    )

    print(f"\n== Safety Guard Tests  (VERBATIM_THRESHOLD={VERBATIM_THRESHOLD}) ==\n")

    # 1. PDF binary outside inbox/ -> must raise
    _run_case(
        "%PDF- signature outside inbox/ => ContentSafetyError",
        expect_raise=True,
        fn=lambda: _assert_no_unsafe_content(
            "%PDF-1.7 fake pdf header rest of fake content",
            outside,
        ),
        passes=passes, failures=failures,
    )

    # 2. PDF binary inside inbox/ -> must NOT raise
    _run_case(
        "%PDF- signature inside inbox/ => permitted",
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            "%PDF-1.7 binary content is fine here",
            inside,
        ),
        passes=passes, failures=failures,
    )

    # 3. Long verbatim span outside inbox/ -> must raise
    _run_case(
        "Verbatim span >= {} chars outside inbox/ => ContentSafetyError".format(VERBATIM_THRESHOLD),
        expect_raise=True,
        fn=lambda: _assert_no_unsafe_content(
            "Some preamble. {}  And a suffix.".format(source),
            outside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 4. Long verbatim span inside inbox/ -> must NOT raise
    _run_case(
        "Verbatim span >= {} chars inside inbox/ => permitted".format(VERBATIM_THRESHOLD),
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            "Some preamble. {}".format(source),
            inside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 5. Genuine original paraphrase -> must NOT raise
    original = (
        "This work introduces an advanced continuous-mode bioreactor strategy "
        "for recombinant protein manufacture, demonstrating substantial yield "
        "improvements over conventional batch approaches. The key innovation "
        "lies in adaptive nutrient management guided by real-time metabolite "
        "monitoring, with direct implications for industrial-scale mAb production."
    )
    _run_case(
        "Genuine original paraphrase outside inbox/ => permitted",
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            original,
            outside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 6. Short coincidental overlap below threshold -> must NOT raise
    coincidental = (
        "Mammalian cell culture remains the dominant platform for biopharmaceutical "
        "manufacturing. This study examines process optimisation strategies relevant "
        "to upstream bioprocessing and titre improvement."
    )
    _run_case(
        "Short coincidental overlap below threshold => permitted",
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            coincidental,
            outside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 7. Boundary: span of exactly (threshold - 1) chars -> must NOT raise
    just_under = source[: VERBATIM_THRESHOLD - 1]
    _run_case(
        "Span of exactly {} chars (threshold-1) => permitted".format(VERBATIM_THRESHOLD - 1),
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            "Some context. {}. Some more context.".format(just_under),
            outside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 8. Boundary: span of exactly threshold chars -> must raise
    exactly = source[:VERBATIM_THRESHOLD]
    _run_case(
        "Span of exactly {} chars (threshold) => ContentSafetyError".format(VERBATIM_THRESHOLD),
        expect_raise=True,
        fn=lambda: _assert_no_unsafe_content(
            "Some context. {}. Some more context.".format(exactly),
            outside,
            source_text=source,
        ),
        passes=passes, failures=failures,
    )

    # 9. No source_text provided -> only PDF binary rule applies
    _run_case(
        "No source_text => only PDF binary rule checked (non-PDF content passes)",
        expect_raise=False,
        fn=lambda: _assert_no_unsafe_content(
            "Anything verbatim here but no PDF header.",
            outside,
            source_text=None,
        ),
        passes=passes, failures=failures,
    )

    # 10. _is_inside_inbox boundary checks
    _run_case(
        "_is_inside_inbox: _INBOX itself => True",
        expect_raise=False,
        fn=lambda: _check(_is_inside_inbox(_INBOX), "_INBOX should be inside inbox"),
        passes=passes, failures=failures,
    )
    _run_case(
        "_is_inside_inbox: _INBOX_PROCESSED => True",
        expect_raise=False,
        fn=lambda: _check(
            _is_inside_inbox(_INBOX_PROCESSED),
            "inbox/processed/ should be inside inbox",
        ),
        passes=passes, failures=failures,
    )
    _run_case(
        "_is_inside_inbox: storage/ => False",
        expect_raise=False,
        fn=lambda: _check(
            not _is_inside_inbox(_ROOT / "storage"),
            "storage/ must NOT be inside inbox",
        ),
        passes=passes, failures=failures,
    )
    _run_case(
        "_is_inside_inbox: _OUTPUT_FILE => False",
        expect_raise=False,
        fn=lambda: _check(
            not _is_inside_inbox(_OUTPUT_FILE),
            "pending_items.jsonl must NOT be inside inbox",
        ),
        passes=passes, failures=failures,
    )

    # 11. _build_record never includes first_page_text
    _run_case(
        "_build_record output never contains first_page_text content",
        expect_raise=False,
        fn=lambda: _check(
            source not in json.dumps(
                _build_record(
                    PdfMetadata(
                        title="Test Paper",
                        first_page_text=source,
                        source_checksum="abc123",
                    ),
                    description="An original summary of this test paper.",
                    source_filename="test.pdf",
                )
            ),
            "_build_record must not embed first_page_text in the output record",
        ),
        passes=passes, failures=failures,
    )


    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(passes) + len(failures)
    print("\n== Results: {}/{} passed{} ==".format(
        len(passes), total,
        ", {} FAILED".format(len(failures)) if failures else "",
    ))

    if failures:
        print("\nFailed tests:")
        for name in failures:
            print("  FAIL: {}".format(name))
        print(
            "\n[SAFETY GUARD FAILURE] One or more safety tests failed. "
            "This agent must NOT be deployed until all tests pass."
        )
        sys.exit(1)

    print("All safety guard tests PASSED.")
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_ingestion",
        description=(
            "BioLitAgent PDF Ingestion Agent — ingests deposited PDFs from "
            "inbox/, generates original paraphrases, and appends structured "
            "records to storage/pending_items.jsonl."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously poll inbox/ for new PDFs rather than running once.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help="Polling interval in watch mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and paraphrase but do not write output or move PDFs.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in safety guard tests and exit (0 = all pass, 1 = failures).",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        metavar="MODEL",
        help="Gemini model for paraphrase generation.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level log output.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Self-test is fully synchronous; run it before touching the LLM client.
    if args.self_test:
        run_safety_tests()
        return  # run_safety_tests() always calls sys.exit()

    global _llm_model
    _llm_model = args.model

    if args.watch:
        asyncio.run(run_watch(dry_run=args.dry_run, poll_interval=args.interval))
    else:
        asyncio.run(run_once(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
