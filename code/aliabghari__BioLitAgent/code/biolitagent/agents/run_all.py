#!/usr/bin/env python3
"""
agents/run_all.py
------------------------------------------------------------------------------
Manager Surface Entry Point for BioLitAgent.

Orchestrates the entire literature monitoring, ingestion, review, and reporting
pipeline on a single on-demand invocation:

  Phase 1: Parallel Ingestion / Scouting
    - Spawns literature_scout, regulatory_watch, and pdf_ingestion in parallel.
    - Waits for all three to complete and append to storage/pending_items.jsonl.
    - Logs start/end timestamps, exit codes, durations, and artifact paths.

  Phase 2: Human Review Checkpoint
    - Blocks for interactive human review via review_checkpoint.py.
    - Allows the reviewer to approve, edit, reject, or skip items.
    - Guarantees human-in-the-loop: writes to permanent storage require
      explicit "CONFIRM".

  Phase 3: Digest Generation (Conditional)
    - ONLY invoked after human approval of items in Phase 2.
    - Reads storage/knowledge_store.db (read-only).
    - Writes a timestamped Word digest: reports/biolitagent_digest_<date>.docx.
    - Updates storage/last_report.json.

  Phase 4: Manager Summary & Transparency Audit
    - Reports total items added during this run.
    - Reports breakdown of items added per chapter (Chapters 1-8).
    - Displays the exact path to the generated .docx file.
    - Outputs a complete artifact audit log showing every file read and written.

Usage
-----
  python agents/run_all.py
  python agents/run_all.py --dry-run
  python agents/run_all.py --skip-scout      # review & report existing pending items
  python agents/run_all.py --force-report   # generate report even if 0 new approvals
  python agents/run_all.py --verbose

Dependencies
------------
  Standard library (asyncio, subprocess, sqlite3, json, time, argparse, etc.)
  No external dependencies required for the orchestrator itself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Optional: python-dotenv ───────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT              = Path(__file__).resolve().parent.parent
_AGENTS_DIR        = _ROOT / "agents"
_STORAGE_DIR       = _ROOT / "storage"
_REPORTS_DIR       = _ROOT / "reports"
_CONFIG_DIR        = _ROOT / "config"
_TEMPLATES_DIR     = _ROOT / "templates"
_INBOX_DIR         = _ROOT / "inbox"

_PENDING_FILE      = _STORAGE_DIR / "pending_items.jsonl"
_DB_FILE           = _STORAGE_DIR / "knowledge_store.db"
_LAST_REPORT_FILE  = _STORAGE_DIR / "last_report.json"
_TAXONOMY_FILE     = _CONFIG_DIR / "chapter_taxonomy.json"
_REG_SOURCES_FILE  = _CONFIG_DIR / "regulatory_sources.json"
_REG_STATE_FILE    = _STORAGE_DIR / "regulatory_state.json"
_LIT_QUERIES_FILE  = _CONFIG_DIR / "literature_queries.json"
_LIT_STATE_FILE    = _STORAGE_DIR / "literature_state.json"

_W = 78  # Width for console banners and dividers

# ── Quota Guard ───────────────────────────────────────────────────────────────
try:
    from biolitagent.config.quota_guard import (
        DEFAULT_DAILY_LIMIT,
        SAFETY_MARGIN,
        check_preflight_gate,
        get_usage_today,
    )
except ImportError:
    try:
        from config.quota_guard import (
            DEFAULT_DAILY_LIMIT,
            SAFETY_MARGIN,
            check_preflight_gate,
            get_usage_today,
        )
    except ImportError:
        DEFAULT_DAILY_LIMIT = 20
        SAFETY_MARGIN = 2
        def check_preflight_gate(estimated_calls: int, agent_name: str) -> bool:
            return True
        def get_usage_today() -> dict[str, Any]:
            return {"calls_made": 0}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("manager_surface")


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class AgentRunResult:
    name:         str
    command:      list[str]
    start_time:   float
    end_time:     float = 0.0
    duration_sec: float = 0.0
    exit_code:    int   = 0
    stdout:       str   = ""
    stderr:       str   = ""
    artifacts_in:  list[str] = field(default_factory=list)
    artifacts_out: list[str] = field(default_factory=list)


@dataclass
class PipelineSummary:
    started_at:         str
    completed_at:       str = ""
    duration_sec:       float = 0.0
    scout_results:      list[AgentRunResult] = field(default_factory=list)
    pending_before:     int = 0
    pending_after:      int = 0
    items_approved:     int = 0
    items_rejected:     int = 0
    items_skipped:      int = 0
    report_generated:   bool = False
    report_path:        Optional[str] = None
    items_per_chapter:  dict[str, int] = field(default_factory=dict)


# ── Console display helpers (ASCII only for Windows cp1252) ───────────────────


def _banner(title: str, subtitle: str = "") -> None:
    print()
    print("=" * _W)
    print("  " + title)
    if subtitle:
        print("  " + subtitle)
    print("=" * _W)


def _section_header(phase_num: int, phase_name: str) -> None:
    print()
    print("-" * _W)
    print("  [PHASE {}] {}".format(phase_num, phase_name.upper()))
    print("-" * _W)


def _log_artifact(action: str, path: Path | str, note: str = "") -> None:
    note_str = f" ({note})" if note else ""
    print("    * {:<7} : {}{}".format(action, path, note_str))


# ── Helper: Count pending items ───────────────────────────────────────────────


def count_pending_items(path: Path = _PENDING_FILE) -> int:
    """Return count of valid JSON lines in pending_items.jsonl."""
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
    except Exception:
        pass
    return count


def get_pending_breakdown(path: Path = _PENDING_FILE) -> dict[str, int]:
    """Return breakdown of pending items by source_type."""
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    src = rec.get("source_type", "unknown")
                    counts[src] = counts.get(src, 0) + 1
                except Exception:
                    pass
    except Exception:
        pass
    return counts


# ── Phase 1: Parallel Scout & Ingest ──────────────────────────────────────────


async def _stream_reader(
    stream: Optional[asyncio.StreamReader],
    prefix: str,
    output_lines: list[str],
    is_stderr: bool = False,
) -> None:
    """Read lines from stream in real time, print with agent prefix, and accumulate."""
    if stream is None:
        return
    target = sys.stderr if is_stderr else sys.stdout
    encoding = getattr(target, "encoding", None) or "ascii"
    while True:
        line_bytes = await stream.readline()
        if not line_bytes:
            break
        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        output_lines.append(line)
        try:
            print(f"{prefix}{line}", file=target, flush=True)
        except UnicodeEncodeError:
            safe_line = line.encode(encoding, errors="replace").decode(encoding)
            print(f"{prefix}{safe_line}", file=target, flush=True)


async def _run_agent_subprocess(
    name: str,
    script_path: Path,
    extra_args: list[str],
    artifacts_in: list[str],
    artifacts_out: list[str],
) -> AgentRunResult:
    """Run an agent script asynchronously as a subprocess with real-time streaming output."""
    cmd = [sys.executable, str(script_path)] + extra_args
    start_t = time.time()
    start_iso = datetime.now(timezone.utc).isoformat()[:19].replace("T", " ")

    print(f"\n  [SPAWN] {name:<18} started at {start_iso}")
    print(f"          Command: {' '.join(cmd)}")

    result = AgentRunResult(
        name=name,
        command=cmd,
        start_time=start_t,
        artifacts_in=artifacts_in,
        artifacts_out=artifacts_out,
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["BIOLITAGENT_ORCHESTRATED"] = "1"

    prefix = f"[{name}] "
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        await asyncio.gather(
            _stream_reader(proc.stdout, prefix, stdout_lines, is_stderr=False),
            _stream_reader(proc.stderr, prefix, stderr_lines, is_stderr=True),
        )

        await proc.wait()
        end_t = time.time()

        result.end_time = end_t
        result.duration_sec = end_t - start_t
        result.exit_code = proc.returncode or 0
        result.stdout = "\n".join(stdout_lines)
        result.stderr = "\n".join(stderr_lines)

        status_str = "[OK]" if result.exit_code == 0 else ("[PARTIAL]" if result.exit_code == 2 else f"[FAIL: exit {result.exit_code}]")
        print(f"  [DONE]  {name:<18} finished in {result.duration_sec:.1f}s -- status: {status_str}")

    except Exception as exc:
        end_t = time.time()
        result.end_time = end_t
        result.duration_sec = end_t - start_t
        result.exit_code = -1
        result.stderr = str(exc)
        print(f"  [FAIL]  {name:<18} exception after {result.duration_sec:.1f}s: {exc}")

    return result


def _format_agent_status(res: AgentRunResult) -> str:
    """
    Format granular agent status, distinguishing partial success from complete failure,
    including daily quota exhaustion states and partial query failures.
    """
    if res.exit_code in (0, 2):
        if res.stdout and ("SKIPPED_QUOTA_EXHAUSTED" in res.stdout or "Daily Gemini quota exhausted" in res.stdout):
            return "[QUOTA_EXHAUSTED: daily limit reached]"
        if res.name == "literature_scout" and (res.exit_code == 2 or "[PARTIAL]" in (res.stdout or "")):
            m = re.search(r"(\d+)\s+queries OK,\s+(\d+)\s+FAILED", res.stdout or "")
            if m:
                return f"[PARTIAL: {m.group(1)} queries OK, {m.group(2)} FAILED]"
            return "[PARTIAL: query failure]"
        if res.exit_code == 0:
            return "[OK]"

    if res.name == "regulatory_watch" and res.stdout:
        # Match lines like: "|  fda-cber-recently-issued     [OK] ITEMS_FOUND"
        source_matches = re.findall(
            r"\|\s+([\w-]+)\s+(?:(\[OK\]|-|\[CACHE_HIT\])|(\[!\]\s+SKIPPED_QUOTA_EXHAUSTED)|(\[X\]|\[!\]))",
            res.stdout,
        )
        if source_matches:
            ok_count = sum(1 for m in source_matches if m[1])
            quota_count = sum(1 for m in source_matches if m[2])
            err_count = sum(1 for m in source_matches if m[3])
            total = ok_count + quota_count + err_count
            parts = []
            if ok_count > 0:
                parts.append(f"{ok_count}/{total} OK")
            if quota_count > 0:
                parts.append(f"{quota_count} QUOTA_SKIPPED")
            if err_count > 0:
                parts.append(f"{err_count} FAILED")
            summary_str = ", ".join(parts) if parts else f"{ok_count}/{total} sources OK"
            return f"{summary_str} [exit {res.exit_code}]"

    return f"[FAILED: exit {res.exit_code}]"


def check_pipeline_preflight_gate(dry_run: bool = False) -> bool:
    """
    Evaluate combined Gemini API call estimates across all 3 monitoring agents:
      - literature_scout: up to 12 calls (configured synthesis cap)
      - pdf_ingestion: count of unread PDFs in inbox/
      - regulatory_watch: count of enabled sources in regulatory_sources.json
    If dry_run is True, returns True without prompting.
    If estimated calls exceed the safe threshold of the shared daily quota,
    prompts the user on the manager surface before any subprocesses are launched.
    Sets BIOLITAGENT_PREFLIGHT_CONFIRMED=1 in os.environ upon confirmation so
    child subprocesses don't prompt a second time.
    """
    if dry_run:
        return True

    # 1. Literature scout estimate: max synthesis calls cap
    lit_calls = 12

    # 2. PDF ingestion estimate: number of PDFs in inbox/
    pdf_calls = 0
    if _INBOX_DIR.exists():
        pdf_calls = len([p for p in _INBOX_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])

    # 3. Regulatory watch estimate: number of enabled sources
    reg_calls = 0
    if _REG_SOURCES_FILE.exists():
        try:
            sources = json.loads(_REG_SOURCES_FILE.read_text(encoding="utf-8")).get("sources", [])
            reg_calls = sum(1 for s in sources if s.get("enabled", True))
        except Exception:
            reg_calls = 4

    total_estimated = lit_calls + pdf_calls + reg_calls

    print(f"\n  [PRE-FLIGHT] Estimating combined pipeline Gemini calls:")
    print(f"    * literature_scout : up to {lit_calls} call(s) (synthesis cap)")
    print(f"    * pdf_ingestion    : up to {pdf_calls} call(s) ({pdf_calls} PDF(s) in inbox/)")
    print(f"    * regulatory_watch : up to {reg_calls} call(s) ({reg_calls} active source(s))")
    print(f"    * Combined Total   : {total_estimated} call(s)")

    passed = check_preflight_gate(total_estimated, "run_all (pipeline)")
    if passed:
        os.environ["BIOLITAGENT_PREFLIGHT_CONFIRMED"] = "1"
        return True

    log.warning("[QUOTA GUARD] Pipeline pre-flight gate aborted by reviewer -- Phase 1 ingestion skipped.")
    return False


async def run_parallel_scouts(
    dry_run: bool = False,
    model: Optional[str] = None,
    verbose: bool = False,
) -> list[AgentRunResult]:
    """
    Spawn literature_scout, regulatory_watch, and pdf_ingestion concurrently.
    Wait for all three to complete before returning.
    """
    _section_header(1, "Parallel Ingestion & Scouting")

    # Combined pre-flight gate across all 3 agents
    if not check_pipeline_preflight_gate(dry_run=dry_run):
        print("  [ABORTED] Phase 1 cancelled by reviewer via Pre-Flight Gate -- 0 API calls made.")
        return []

    print("  Spawning 3 monitoring agents concurrently:")
    print("    1. literature_scout   -> PubMed / bioRxiv literature search")
    print("    2. regulatory_watch   -> FDA / EMA / ICH guidance tracker")
    print("    3. pdf_ingestion      -> Local inbox/ PDF watcher & summarizer")
    print()
    print("  Shared output artifact: storage/pending_items.jsonl")

    shared_args = []
    if dry_run:
        shared_args.append("--dry-run")
    if model:
        shared_args.extend(["--model", model])
    if verbose:
        shared_args.append("--verbose")

    # Define agents to run
    tasks = [
        _run_agent_subprocess(
            name="literature_scout",
            script_path=_AGENTS_DIR / "literature_scout.py",
            extra_args=shared_args,
            artifacts_in=[str(_LIT_QUERIES_FILE), str(_LIT_STATE_FILE)],
            artifacts_out=[str(_PENDING_FILE), str(_LIT_STATE_FILE)],
        ),
        _run_agent_subprocess(
            name="regulatory_watch",
            script_path=_AGENTS_DIR / "regulatory_watch.py",
            extra_args=shared_args,
            artifacts_in=[str(_REG_SOURCES_FILE), str(_REG_STATE_FILE)],
            artifacts_out=[str(_PENDING_FILE), str(_REG_STATE_FILE)],
        ),
        _run_agent_subprocess(
            name="pdf_ingestion",
            script_path=_AGENTS_DIR / "pdf_ingestion.py",
            extra_args=shared_args,
            artifacts_in=[str(_INBOX_DIR)],
            artifacts_out=[str(_PENDING_FILE), str(_INBOX_DIR / "processed")],
        ),
    ]

    results = await asyncio.gather(*tasks)

    print()
    print("  -- Phase 1 Ingestion Audit --")
    write_action = "[DRY RUN] would write" if dry_run else "wrote"
    for res in results:
        status_disp = _format_agent_status(res)
        tag = "[OK]  " if res.exit_code == 0 else ("[PARTIAL]" if res.exit_code == 2 else f"[ERR:{res.exit_code}]")
        detail_note = f" ({status_disp})" if status_disp != "[OK]" else ""
        print(f"    {tag} {res.name:<18} took {res.duration_sec:>5.1f}s{detail_note}")
        for art in res.artifacts_out:
            _log_artifact(write_action, art)

    return list(results)


# ── Phase 2: Human Review Checkpoint ──────────────────────────────────────────


def run_review_checkpoint() -> tuple[int, int, int, int]:
    """
    Invoke review_checkpoint.py interactively, blocking until human review ends.

    Returns:
      (exit_code, items_approved, items_rejected, items_skipped)
    """
    _section_header(2, "Human Review Checkpoint")
    print("  Artifacts involved:")
    _log_artifact("read", _PENDING_FILE, "pending items awaiting review")
    _log_artifact("read", _TAXONOMY_FILE, "13-tag bioprocess chapter taxonomy")
    _log_artifact("write", _DB_FILE, "permanent append-only knowledge store")
    print()
    print("  Launching interactive review surface. Reviewer input required...")
    print("  (Approval, edits, or rejections will be requested per item)")
    print()

    # Query DB approval_runs before the review session
    db_existed_before = _DB_FILE.exists()
    runs_before = 0
    items_before = 0
    if db_existed_before:
        try:
            conn = sqlite3.connect(str(_DB_FILE))
            runs_before = conn.execute("SELECT COUNT(*) FROM approval_runs").fetchone()[0]
            items_before = conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0]
            conn.close()
        except Exception:
            pass

    cmd = [sys.executable, str(_AGENTS_DIR / "review_checkpoint.py")]
    start_t = time.time()

    # Pass stdin/stdout/stderr directly to parent process so interactive input works
    proc = subprocess.run(cmd)
    duration = time.time() - start_t

    approved = 0
    rejected = 0
    skipped  = 0

    if _DB_FILE.exists():
        try:
            conn = sqlite3.connect(str(_DB_FILE))
            conn.row_factory = sqlite3.Row
            items_after = conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0]
            approved = items_after - items_before

            # Check latest run record for rejected and skipped counts
            last_run = conn.execute(
                "SELECT * FROM approval_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if last_run:
                rejected = last_run["items_rejected"] or 0
                skipped  = last_run["items_skipped"] or 0
            conn.close()
        except Exception as exc:
            log.warning("Could not read approval run stats: %s", exc)

    print()
    print("  -- Phase 2 Review Audit --")
    print(f"    Duration  : {duration:.1f}s")
    print(f"    Exit code : {proc.returncode}")
    print(f"    Approved  : {approved} item(s)")
    print(f"    Rejected  : {rejected} item(s)")
    print(f"    Skipped   : {skipped} item(s) (remain in pending)")

    return proc.returncode, approved, rejected, skipped


# ── Phase 3: Report Generator ──────────────────────────────────────────────────


def run_report_generator(dry_run: bool = False, verbose: bool = False) -> tuple[int, Optional[str]]:
    """
    Invoke report_generator.py to produce the updated Word digest.

    Returns:
      (exit_code, generated_report_path)
    """
    _section_header(3, "Digest Generation")
    print("  Artifacts involved:")
    _log_artifact("read", _DB_FILE, "knowledge store (PRAGMA query_only=ON)")
    _log_artifact("read", _LAST_REPORT_FILE, "previous report cutoff state")
    _log_artifact("read", _TEMPLATES_DIR / "digest_template.docx", "Word document template")
    _log_artifact("write", _REPORTS_DIR, "new timestamped biolitagent_digest_<date>.docx")
    print()

    cmd = [sys.executable, str(_AGENTS_DIR / "report_generator.py")]
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("--verbose")

    start_t = time.time()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    prefix = "[report_generator] "
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    if proc.stdout:
        for line in proc.stdout:
            raw_line = line.rstrip()
            try:
                print(f"{prefix}{raw_line}", flush=True)
            except UnicodeEncodeError:
                safe_line = raw_line.encode(encoding, errors="replace").decode(encoding)
                print(f"{prefix}{safe_line}", flush=True)
    proc.wait()
    duration = time.time() - start_t

    report_path = None
    if _LAST_REPORT_FILE.exists():
        try:
            state = json.loads(_LAST_REPORT_FILE.read_text(encoding="utf-8"))
            report_path = state.get("last_report_file")
        except Exception:
            pass

    print()
    print("  -- Phase 3 Report Audit --")
    print(f"    Duration  : {duration:.1f}s")
    print(f"    Exit code : {proc.returncode}")
    if report_path:
        _log_artifact("created", report_path, "new Word digest")

    return proc.returncode, report_path


# ── Phase 4: Manager Summary & Transparency Audit ─────────────────────────────


def get_items_added_per_chapter(since_iso: Optional[str] = None) -> dict[str, int]:
    """
    Query knowledge_store.db to calculate items added per report chapter.
    Uses the 12-tag to 8-chapter mapping defined in report_generator.CHAPTERS.
    """
    if not _DB_FILE.exists():
        return {}

    # Chapter mapping imported directly from report_generator to avoid duplication
    try:
        from biolitagent.agents.report_generator import CHAPTERS
    except ImportError:
        try:
            from agents.report_generator import CHAPTERS
        except ImportError:
            from report_generator import CHAPTERS

    chapter_map: list[tuple[int, str, list[str]]] = [
        (c.number, c.title, c.tags) for c in CHAPTERS
    ]

    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(str(_DB_FILE))
        conn.row_factory = sqlite3.Row

        # Items added in the most recent approval run
        last_run = conn.execute(
            "SELECT run_id, started_at FROM approval_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        if not last_run:
            conn.close()
            return {}

        latest_run_id = last_run["run_id"]
        run_items = conn.execute(
            "SELECT chapter_tag FROM knowledge_items WHERE run_id = ?",
            (latest_run_id,),
        ).fetchall()

        tag_counts: dict[str, int] = {}
        for row in run_items:
            t = row["chapter_tag"]
            tag_counts[t] = tag_counts.get(t, 0) + 1

        # Chapter 1 is the total items in this run
        counts["1. Executive Summary - What's New"] = len(run_items)

        # Chapters 2-8
        for num, title, tags in chapter_map[1:]:
            c = sum(tag_counts.get(t, 0) for t in tags)
            counts[f"{num}. {title}"] = c

        conn.close()
    except Exception as exc:
        log.warning("Could not calculate chapter breakdown: %s", exc)

    return counts


def print_manager_summary(summary: PipelineSummary) -> None:
    """Print the final executive summary dashboard and artifact audit log."""
    _banner(
        "BioLitAgent Run Summary & Transparency Dashboard",
        f"Completed at {summary.completed_at[:19]} UTC  (Total duration: {summary.duration_sec:.1f}s)",
    )

    print("\n  1. INGESTION & PIPELINE METRICS")
    if summary.scout_results:
        agent_statuses = ", ".join(
            f"{r.name}: {_format_agent_status(r)}"
            for r in summary.scout_results
        )
        print(f"     * Ingestion agent status   : {agent_statuses}")
    else:
        print("     * Ingestion agent status   : (scouting phase skipped)")
    print(f"     * Pending items before run : {summary.pending_before}")
    print(f"     * Pending items after run  : {summary.pending_after}")
    print(f"     * Items approved this run  : {summary.items_approved}")
    print(f"     * Items rejected this run  : {summary.items_rejected}")
    print(f"     * Items skipped for later  : {summary.items_skipped}")

    print("\n  2. CHAPTER BREAKDOWN (Items added to knowledge store)")
    if summary.items_per_chapter:
        for ch_name, count in summary.items_per_chapter.items():
            bar = "#" * min(count * 2, 20)
            print(f"     {ch_name:<50} : {count:>2} item(s)  {bar}")
    else:
        print("     (No new items were committed to chapters this run)")

    print("\n  3. GENERATED DELIVERABLES")
    if summary.report_generated and summary.report_path:
        print(f"     * Digest document (.docx) : {summary.report_path}")
        print(f"     * Status                  : SUCCESSFULLY GENERATED & SAVED")
    elif not summary.report_generated:
        print("     * Digest document (.docx) : NOT GENERATED")
        print("       Reason: Report generator only runs after human approval.")
        print("       (No items were approved during this session).")

    print("\n  4. ARTIFACT AUDIT LOG (Transparency Trail)")
    print("     The following state and data artifacts govern this pipeline:")
    _log_artifact("STATE ", _REG_STATE_FILE, "Last-seen hashes for FDA/EMA/ICH guidance pages")
    _log_artifact("STATE ", _LIT_STATE_FILE, "Seen PMIDs/DOIs for PubMed and bioRxiv")
    _log_artifact("QUEUE ", _PENDING_FILE, "Staging queue for unapproved incoming items")
    _log_artifact("STORE ", _DB_FILE, "Permanent append-only knowledge store (SQLite)")
    _log_artifact("STATE ", _LAST_REPORT_FILE, "Timestamp cutoff for Chapter 1 (What's New)")
    if summary.report_path:
        _log_artifact("OUTPUT", summary.report_path, "Client-ready Word digest")

    print("\n" + "=" * _W + "\n")


# ── Full Pipeline Orchestration ───────────────────────────────────────────────


async def run_pipeline(
    dry_run:      bool = False,
    skip_scout:   bool = False,
    force_report: bool = False,
    model:        Optional[str] = None,
    verbose:      bool = False,
) -> int:
    """Run the complete 4-phase BioLitAgent manager workflow."""
    start_time_mono = time.time()
    started_at_iso = datetime.now(timezone.utc).isoformat()

    _banner(
        "BioLitAgent Manager Surface",
        "Autonomous Literature Monitoring -> Human Review Checkpoint -> Regenerated Digest",
    )
    print(f"  Run started at {started_at_iso[:19]} UTC")
    if dry_run:
        print("  MODE: DRY-RUN (No persistent state or database changes will be saved)")

    summary = PipelineSummary(started_at=started_at_iso)
    summary.pending_before = count_pending_items()

    # ── Phase 1: Parallel Scout & Ingestion ──────────────────────────────────
    if not skip_scout:
        summary.scout_results = await run_parallel_scouts(
            dry_run=dry_run,
            model=model,
            verbose=verbose,
        )
    else:
        print("\n  [PHASE 1 SKIPPED] --skip-scout flag specified. Proceeding to review.")

    summary.pending_after = count_pending_items()
    pending_diff = summary.pending_after - summary.pending_before
    breakdown = get_pending_breakdown()
    print(f"\n  Staging Queue Status: {summary.pending_after} total pending item(s) (+{pending_diff} this run)")
    if breakdown:
        for st, c in breakdown.items():
            print(f"    - {st:<16}: {c} item(s)")

    # ── Phase 2: Human Review Checkpoint ────────────────────────────────────
    rc_exit, approved, rejected, skipped = run_review_checkpoint()
    summary.items_approved = approved
    summary.items_rejected = rejected
    summary.items_skipped  = skipped

    if rc_exit != 0:
        log.warning("Review checkpoint exited with code %d", rc_exit)

    # ── Phase 3: Digest Generation ──────────────────────────────────────────
    # STRICT RULE: Only after approval, invoke report_generator.py
    if approved > 0 or force_report:
        if force_report and approved == 0:
            print("\n  [NOTICE] --force-report specified: generating digest with existing knowledge store.")
        rep_exit, report_path = run_report_generator(dry_run=dry_run, verbose=verbose)
        summary.report_generated = (rep_exit == 0 and report_path is not None)
        summary.report_path = report_path
    else:
        print("\n  [PHASE 3 SKIPPED] No new items approved during this review checkpoint.")
        print("  Per pipeline specification, report_generator.py is only invoked after approval.")
        summary.report_generated = False

    # ── Phase 4: Summary & Dashboard ────────────────────────────────────────
    summary.items_per_chapter = get_items_added_per_chapter()
    end_time_mono = time.time()
    summary.duration_sec = end_time_mono - start_time_mono
    summary.completed_at = datetime.now(timezone.utc).isoformat()

    print_manager_summary(summary)

    return 0


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_all",
        description="BioLitAgent Manager Surface -- single on-demand pipeline runner.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all agents in dry-run mode (no files or DB records saved).",
    )
    parser.add_argument(
        "--skip-scout",
        action="store_true",
        help="Skip Phase 1 (parallel scouting) and proceed directly to review.",
    )
    parser.add_argument(
        "--force-report",
        action="store_true",
        help="Generate report even if 0 items were approved during this session.",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Override Gemini model used by sub-agents.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging across all agents.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    return asyncio.run(
        run_pipeline(
            dry_run=args.dry_run,
            skip_scout=args.skip_scout,
            force_report=args.force_report,
            model=args.model,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
