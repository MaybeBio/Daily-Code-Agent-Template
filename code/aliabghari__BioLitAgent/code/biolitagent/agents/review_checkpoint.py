#!/usr/bin/env python3
"""
agents/review_checkpoint.py
--------------------------------------------------------------------------------
Review Checkpoint Agent for BioLitAgent.

Interactive terminal CLI for a human reviewer to inspect, tag, edit, approve,
or reject every pending item before anything is committed to the permanent
knowledge store.  Explicit human confirmation is required at every write —
there is no auto-approval path.

HUMAN-IN-THE-LOOP GUARANTEE
----------------------------
Nothing is written to knowledge_store.db and nothing is removed from
pending_items.jsonl until the reviewer types the word CONFIRM at the final
prompt.  Every code path that leads to a write goes through write_approved(),
which is only reachable after request_confirmation() returns True.

Workflow
--------
  1. Load storage/pending_items.jsonl; skip items already in knowledge_store.db
     (safety net for crash-recovery scenarios).
  2. Auto-suggest a chapter tag for each item using keyword matching against
     config/chapter_taxonomy.json.
  3. Print an overview table grouped by proposed chapter tag.
  4. Review items one by one:
       [A] Approve  [E] Edit (title/description/tag/note)  [R] Reject
       [S] Skip     [B] Batch-approve all remaining        [Q] Quit
  5. Print a pre-commit summary showing what will be committed, removed, or
     kept in pending.
  6. Require the reviewer to type exactly CONFIRM before any write occurs.
  7. On CONFIRM:
       a. Append approved items to knowledge_store.db (single transaction).
       b. Rewrite pending_items.jsonl keeping only skipped items.
     All writes are all-or-nothing; if the DB insert fails, nothing is rewritten.

Knowledge store schema
----------------------
  approval_runs     — one row per review session (run_id, timestamps, counts)
  knowledge_items   — one row per approved item (APPEND-ONLY, never UPDATE/DELETE)
      pending_id    UNIQUE  — prevents double-committing the same pending item
      reviewer_action CHECK = 'approved'  — rejected items are never inserted

Usage
-----
  python agents/review_checkpoint.py
  python agents/review_checkpoint.py --pending PATH   # override input file
  python agents/review_checkpoint.py --db PATH        # override DB path
  python agents/review_checkpoint.py --taxonomy PATH  # override taxonomy

Dependencies
------------
  Standard library only (sqlite3, json, textwrap, argparse, uuid, ...).
  No third-party packages required.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_ROOT             = Path(__file__).resolve().parent.parent
_DEFAULT_PENDING  = _ROOT / "storage" / "pending_items.jsonl"
_DEFAULT_DB       = _ROOT / "storage" / "knowledge_store.db"
_DEFAULT_TAXONOMY = _ROOT / "config" / "chapter_taxonomy.json"
_DEFAULT_REJECTED_LOG = _ROOT / "storage" / "rejected_items_log.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

_W = 78   # effective line width for separators


def _sep(char: str = "-", width: int = _W) -> str:
    return char * width


def _wrap(text: str, indent: int = 4, width: int = _W) -> str:
    pad = " " * indent
    return textwrap.fill(
        text or "(none)",
        width=width,
        initial_indent=pad,
        subsequent_indent=pad,
    )


def _trunc(s: str, n: int) -> str:
    """Truncate *s* to *n* chars, appending '...' if trimmed."""
    s = str(s or "")
    return s if len(s) <= n else s[: n - 3] + "..."


def _banner(run_id: str) -> None:
    print()
    print("=" * _W)
    left  = "  BioLitAgent Review Checkpoint"
    right = "Run " + run_id[:8]
    gap   = max(1, _W - len(left) - len(right) - 2)
    print(left + " " * gap + right)
    print("=" * _W)


def _section(title: str) -> None:
    print()
    print("  -- " + title + " --")
    print(_sep())


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS approval_runs (
    run_id         TEXT    PRIMARY KEY,
    started_at     TEXT    NOT NULL,
    completed_at   TEXT,
    items_reviewed INTEGER DEFAULT 0,
    items_approved INTEGER DEFAULT 0,
    items_rejected INTEGER DEFAULT 0,
    items_skipped  INTEGER DEFAULT 0,
    reviewer       TEXT
);

-- APPEND-ONLY: this table is never modified after INSERT.
-- The UNIQUE constraint on pending_id prevents double-committing the same item.
-- reviewer_action is constrained to 'approved'; rejected items are never stored.
CREATE TABLE IF NOT EXISTS knowledge_items (
    store_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_id      TEXT    NOT NULL UNIQUE,
    run_id          TEXT    NOT NULL REFERENCES approval_runs(run_id),
    source_type     TEXT    NOT NULL,
    chapter_tag     TEXT    NOT NULL,
    title           TEXT,
    description     TEXT    NOT NULL,
    metadata_json   TEXT    NOT NULL,
    reviewer_note   TEXT,
    reviewed_at     TEXT    NOT NULL,
    reviewer_action TEXT    NOT NULL CHECK(reviewer_action = 'approved')
);

CREATE INDEX IF NOT EXISTS idx_ki_tag    ON knowledge_items(chapter_tag);
CREATE INDEX IF NOT EXISTS idx_ki_run    ON knowledge_items(run_id);
CREATE INDEX IF NOT EXISTS idx_ki_source ON knowledge_items(source_type);
CREATE INDEX IF NOT EXISTS idx_ki_date   ON knowledge_items(reviewed_at);
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite knowledge store and apply the DDL."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    try:
        conn.execute("ALTER TABLE approval_runs ADD COLUMN reviewer TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def already_approved_ids(conn: sqlite3.Connection) -> set[str]:
    """Return all pending_ids already committed to knowledge_items."""
    return {r["pending_id"] for r in conn.execute("SELECT pending_id FROM knowledge_items").fetchall()}


def last_run_completed_at(conn: sqlite3.Connection) -> Optional[str]:
    """Return the ISO timestamp of the most recent completed run, or None."""
    row = conn.execute(
        "SELECT completed_at FROM approval_runs "
        "WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    return row["completed_at"] if row else None


def create_run_record(conn: sqlite3.Connection, run_id: str, reviewer: str = "human_reviewer") -> None:
    conn.execute(
        "INSERT INTO approval_runs (run_id, started_at, reviewer) VALUES (?, ?, ?)",
        (run_id, datetime.now(timezone.utc).isoformat(), reviewer),
    )
    conn.commit()


def update_run_record(
    conn:     sqlite3.Connection,
    run_id:   str,
    approved: int,
    rejected: int,
    skipped:  int,
    reviewer: Optional[str] = None,
) -> None:
    if reviewer:
        conn.execute(
            """UPDATE approval_runs
               SET completed_at = ?, items_reviewed = ?,
                   items_approved = ?, items_rejected = ?, items_skipped = ?,
                   reviewer = ?
               WHERE run_id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                approved + rejected + skipped,
                approved, rejected, skipped,
                reviewer,
                run_id,
            ),
        )
    else:
        conn.execute(
            """UPDATE approval_runs
               SET completed_at = ?, items_reviewed = ?,
                   items_approved = ?, items_rejected = ?, items_skipped = ?
               WHERE run_id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                approved + rejected + skipped,
                approved, rejected, skipped,
                run_id,
            ),
        )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Taxonomy
# ─────────────────────────────────────────────────────────────────────────────


def load_taxonomy(path: Path) -> list[dict[str, Any]]:
    """Load and return the list of chapter-tag dicts from *path*."""
    if not path.exists():
        raise FileNotFoundError(
            "Chapter taxonomy not found: {}\n"
            "  Expected: config/chapter_taxonomy.json".format(path)
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    tags = data.get("tags", [])
    if not tags:
        raise ValueError("No tags found in {}".format(path))
    return tags


# Domain-specific terms that strongly identify unit operations receive higher weights.
# This prevents generic overlap terms (e.g. "optimization" in hybrid_modeling)
# from overriding explicit process operations (e.g. "perfusion", "CHO cells" in upstream_process).
KEYWORD_WEIGHT_OVERRIDES: dict[str, dict[str, int]] = {
    "upstream_process": {
        "perfusion": 4,
        "perfusion processes": 4,
        "perfusion process": 4,
        "bioreactor": 3,
        "cho": 3,
        "cho cells": 4,
        "chinese hamster ovary": 4,
        "viable cell density": 4,
        "vcd": 3,
        "fed-batch": 3,
        "cell culture": 3,
        "volumetric productivity": 3,
        "specific productivity": 3,
        "seed train": 3,
        "n-1 perfusion": 4,
        "recombinant subunit vaccine": 3,
    },
    "downstream_process": {
        "protein a": 4,
        "affinity chromatography": 4,
        "purification": 3,
        "tangential flow": 3,
        "ultrafiltration": 3,
        "diafiltration": 3,
        "viral clearance": 4,
        "continuous capture chromatography": 4,
        "breakthrough curve": 4,
    },
    "analytical_characterization": {
        "glycosylation": 4,
        "mass spectrometry": 4,
        "charge variant": 4,
        "potency assay": 4,
        "hplc": 3,
        "cqa": 3,
        "fc glycan": 4,
        "fc glycans": 4,
    },
    "hybrid_modeling": {
        "digital twin": 4,
        "hybrid model": 4,
        "hybrid modeling": 4,
        "surrogate model": 4,
        "neural network": 3,
        "machine learning": 3,
        "mechanistic model": 3,
        "process control": 2,
        "ai/ml": 3,
        "intelligent manufacturing": 3,
        "hybrid framework": 3,
        "optimization": 0,
        "simulation": 1,
    },
    "microbiome_platform_science": {
        "live biotherapeutic": 4,
        "live biotherapeutic product": 4,
        "lbp": 3,
        "commensal": 4,
        "commensal vaccine": 4,
        "engineered probiotic": 4,
        "engineered bacterial therapeutic": 4,
        "engineered microbial therapeutic": 4,
        "microbial therapeutics": 4,
        "synthetic biology": 3,
        "bacteroides": 3,
        "microbiome": 0,
        "gut microbiota": 1,
        "gut microbiome": 1,
    },
}


def suggest_tag(item: dict[str, Any], taxonomy: list[dict[str, Any]]) -> Optional[str]:
    """
    Return the best-matching chapter tag id for *item* by weighted keyword scoring.

    Searches the concatenated title + description + agency fields against each
    tag's keyword list. Upstream-process-specific terms (perfusion, CHO, viable
    cell density, bioreactor) are weighted more heavily than generic modeling
    terms (optimization, simulation) to prevent mis-tagging.
    Requires best_score >= 2 to avoid tagging generic single-word hits without process anchors.

    Priority hierarchy:
      1. Standard chapters (Chapters 1-11, excluding emerging_topics) are scored first.
         If any standard chapter scores >= 2, that chapter is assigned.
      2. emerging_topics is a last resort: it is only evaluated when NO other chapter
         scores above the minimum threshold (>= 2).
    """
    text = " ".join(filter(None, [
        item.get("title") or "",
        item.get("description") or "",
        item.get("agency") or "",
    ])).lower()

    # Step 1: Score all standard chapters (excluding emerging_topics)
    best_id:    Optional[str] = None
    best_score: int           = 0
    emerging_def: Optional[dict[str, Any]] = None

    for tag_def in taxonomy:
        tag_id = tag_def["id"]
        if tag_id == "emerging_topics":
            emerging_def = tag_def
            continue

        weights = KEYWORD_WEIGHT_OVERRIDES.get(tag_id, {})
        score = 0
        seen_kws = set()

        for kw in tag_def.get("keywords", []):
            kw_lower = kw.lower()
            if kw_lower in text and kw_lower not in seen_kws:
                score += weights.get(kw_lower, 1)
                seen_kws.add(kw_lower)

        for extra_kw, extra_weight in weights.items():
            if extra_kw in text and extra_kw not in seen_kws:
                score += extra_weight
                seen_kws.add(extra_kw)

        # CQA pairing with glycan/structure terms for analytical_characterization
        if tag_id == "analytical_characterization":
            has_cqa = "critical quality attribute" in text or "cqa" in text
            has_glycan_or_struct = any(
                term in text
                for term in ("glycan", "glycans", "fc glycan", "fc glycans", "glycosylation", "higher order structure", "charge variant", "peptide mapping", "disulfide bond")
            )
            if has_cqa and has_glycan_or_struct:
                score += 3

        if score > best_score:
            best_score = score
            best_id    = tag_id

    # If any standard chapter scores >= 2, assign that chapter!
    if best_score >= 2:
        return best_id

    # Step 2: Only when NO other chapter meets the confident-match threshold (>= 2),
    # consider emerging_topics as a last resort.
    if emerging_def is not None:
        em_score = 0
        em_seen = set()
        em_weights = KEYWORD_WEIGHT_OVERRIDES.get("emerging_topics", {})
        for kw in emerging_def.get("keywords", []):
            kw_lower = kw.lower()
            if kw_lower in text and kw_lower not in em_seen:
                em_score += em_weights.get(kw_lower, 1)
                em_seen.add(kw_lower)

        for extra_kw, extra_weight in em_weights.items():
            if extra_kw in text and extra_kw not in em_seen:
                em_score += extra_weight
                em_seen.add(extra_kw)

        if em_score >= 2:
            return "emerging_topics"

    return None


def tag_label(tag_id: Optional[str], taxonomy: list[dict[str, Any]]) -> str:
    """Return the human-readable label for a tag id, or the id itself."""
    for t in taxonomy:
        if t["id"] == tag_id:
            return t.get("label", tag_id)
    return tag_id or "(untagged)"


# ─────────────────────────────────────────────────────────────────────────────
# Pending items
# ─────────────────────────────────────────────────────────────────────────────


def load_pending(path: Path) -> list[dict[str, Any]]:
    """Load all items from *path* (JSONL).  Invalid lines are skipped with a warning."""
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                items.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print("  WARNING: pending_items.jsonl line {} invalid JSON — skipped. ({})".format(lineno, exc))
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Overview display
# ─────────────────────────────────────────────────────────────────────────────


def print_overview(
    tagged: list[tuple[Optional[str], dict[str, Any]]],
    taxonomy: list[dict[str, Any]],
) -> None:
    """
    Print a table of all pending items grouped by proposed chapter tag.

    *tagged* is a list of (suggested_tag_or_None, item) pairs in review order.
    """
    n_total = len(tagged)
    _section("Overview: {} item(s) to review".format(n_total))

    # Group by tag, preserving the review-order numbering.
    tag_order = [t["id"] for t in taxonomy]
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for idx, (tag, item) in enumerate(tagged, 1):
        key = tag or "(untagged)"
        groups.setdefault(key, []).append((idx, item))

    # Print named tags in taxonomy order, then (untagged).
    ordered_keys = sorted(
        groups.keys(),
        key=lambda k: tag_order.index(k) if k in tag_order else 9999,
    )

    for key in ordered_keys:
        entries = groups[key]
        label   = tag_label(key if key != "(untagged)" else None, taxonomy)
        bar     = "#" * min(len(entries) * 3, 18)
        print()
        print("  [ {} ]  {}  {} item(s)".format(key, bar, len(entries)))
        for num, item in entries:
            match_pct = item.get("match_percentage")
            pct_str = f" ({round(match_pct)}%)" if match_pct is not None else ""
            stale_str = " [STALE]" if item.get("stale") is True else ""
            badges = f"{pct_str}{stale_str}"
            max_len = max(20, 62 - len(badges))
            title = _trunc(item.get("title") or "(no title)", max_len)
            print(f"  {num:>4}. {title}{badges}")


# ─────────────────────────────────────────────────────────────────────────────
# Per-item display
# ─────────────────────────────────────────────────────────────────────────────


def print_item(
    item:  dict[str, Any],
    index: int,
    total: int,
) -> None:
    """Print a full single-item view for the review menu."""
    source  = item.get("source_type", "unknown")
    agency  = item.get("agency", "")
    tag     = item.get("chapter_tag") or "(untagged)"

    print()
    print(_sep())
    left  = "  Item {}/{}   source: {}{}   tag: {}".format(
        index, total, source,
        "   agency: " + agency if agency else "",
        tag,
    )
    print(left)
    print(_sep())
    print("  Title      : " + _trunc(item.get("title") or "(no title)", _W - 15))

    if source == "regulatory":
        pub = item.get("publication_date") or ("(not found)" if item.get("date_unknown") else "")
        if pub:
            print("  Pub date   : " + pub)
        url = item.get("url") or ("(not found on page)" if item.get("url_unknown") else "")
        if url:
            print("  URL        : " + _trunc(url, _W - 15))
    elif source in ("deposited_pdf", "literature", "pubmed", "biorxiv"):
        authors = item.get("authors") or []
        if authors:
            print("  Authors    : " + _trunc(", ".join(authors[:4]), _W - 15))
        if item.get("publication_year"):
            print("  Year       : {}".format(item["publication_year"]))
        if item.get("doi"):
            print("  DOI        : " + _trunc(item["doi"], _W - 15))
        if item.get("url"):
            print("  URL        : " + _trunc(item["url"], _W - 15))

    match_pct = item.get("match_percentage")
    bonus = item.get("recency_bonus")
    stale = item.get("stale")
    year_unknown = item.get("year_unknown")

    rel_parts = []
    if match_pct is not None:
        rel_parts.append(f"Match: {round(match_pct)}%")
    if bonus is not None and bonus > 0:
        rel_parts.append(f"Recency Bonus: +{bonus:.1f}")
    if stale is True:
        rel_parts.append("[STALE]")
    elif year_unknown is True:
        rel_parts.append("[YEAR UNKNOWN]")

    if rel_parts:
        print("  Relevance  : " + " | ".join(rel_parts))

    detected = (item.get("detected_at") or "")[:19].replace("T", " ")
    print("  Detected   : {} UTC".format(detected))
    print()
    print("  Description:")
    desc = item.get("description") or "(no description)"
    if item.get("synthesis_method") == "fallback_template":
        desc = f"[TEMPLATE] {desc}"
    print(_wrap(desc, indent=4))

    note = item.get("reviewer_note")
    if note:
        print()
        print("  Reviewer note:")
        print(_wrap(note, indent=4))


# ─────────────────────────────────────────────────────────────────────────────
# Edit dialog
# ─────────────────────────────────────────────────────────────────────────────


def edit_dialog(item: dict[str, Any], taxonomy: list[dict[str, Any]]) -> None:
    """
    Let the reviewer edit item fields in-place.

    Editable fields: title, description (multi-line), chapter tag, reviewer note.
    All changes are applied to the *item* dict directly; nothing is written to
    disk at this stage.
    """
    while True:
        print()
        print("  -- Edit Item --")
        print("  [1] Title         (current: {})".format(_trunc(item.get("title") or "(none)", 52)))
        print("  [2] Description   (see above)")
        print("  [3] Chapter tag   (current: {})".format(item.get("chapter_tag") or "(untagged)"))
        print("  [4] Reviewer note")
        print("  [5] Done")
        print()

        try:
            sub = input("  Edit [1-5]: ").strip()
        except KeyboardInterrupt:
            print()
            break

        if sub == "1":
            print("  Current title: {}".format(item.get("title") or "(none)"))
            try:
                new = input("  New title (blank to keep): ").strip()
            except KeyboardInterrupt:
                print()
                continue
            if new:
                item["title"] = new
                print("  Title updated.")

        elif sub == "2":
            print("  Current description:")
            desc = item.get("description") or "(none)"
            if item.get("synthesis_method") == "fallback_template":
                desc = f"[TEMPLATE] {desc}"
            print(_wrap(desc, indent=4))
            print()
            print("  Enter new description.  Blank line ends entry; blank first line keeps current.")
            lines: list[str] = []
            try:
                while True:
                    line = input("  > ")
                    if not line and not lines:
                        break   # empty first line = keep current
                    if not line:
                        break   # empty follow-on line = end of input
                    lines.append(line)
            except KeyboardInterrupt:
                print()
                lines = []
            if lines:
                item["description"] = " ".join(lines)
                item["synthesis_method"] = "reviewer_edited"
                print("  Description updated.")

        elif sub == "3":
            print()
            print("  Available chapter tags:")
            current_tag = item.get("chapter_tag")
            for i, t in enumerate(taxonomy, 1):
                marker = "  <-- current" if t["id"] == current_tag else ""
                print("    [{:>2}] {:<40} {}{}".format(i, t["id"], t.get("label", ""), marker))
            print("    [ 0] Keep current ({})".format(current_tag or "untagged"))
            print()
            while True:
                try:
                    raw = input("  Tag number (0 to keep): ").strip()
                except KeyboardInterrupt:
                    print()
                    raw = "0"
                if raw == "0" or raw == "":
                    break
                if raw.isdigit():
                    idx = int(raw) - 1
                    if 0 <= idx < len(taxonomy):
                        item["chapter_tag"] = taxonomy[idx]["id"]
                        print("  Tag set to: {}".format(taxonomy[idx]["id"]))
                        break
                print("  Invalid — enter 0 to {}.".format(len(taxonomy)))

        elif sub == "4":
            existing = item.get("reviewer_note") or ""
            if existing:
                print("  Current note: {}".format(existing))
            try:
                new = input("  Reviewer note (blank to keep): ").strip()
            except KeyboardInterrupt:
                print()
                continue
            if new:
                item["reviewer_note"] = new
                print("  Note saved.")

        elif sub == "5":
            break
        else:
            print("  Invalid choice.")


# ─────────────────────────────────────────────────────────────────────────────
# Review loop
# ─────────────────────────────────────────────────────────────────────────────


def review_items(
    items:    list[dict[str, Any]],
    taxonomy: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Run the interactive per-item review loop.

    Items are pre-sorted by auto-suggested chapter tag (taxonomy order) so the
    reviewer encounters related items together.

    Returns (approved, rejected, skipped).

    Safety guarantees:
      - Nothing is written to disk inside this function.
      - On [Q] or Ctrl-C, returns ([], [], all_original_items) so the caller
        sees zero approved/rejected and leaves pending_items.jsonl unchanged.
    """
    # Pre-compute suggested tags and sort by tag for natural review flow.
    tag_order = {t["id"]: i for i, t in enumerate(taxonomy)}

    tagged: list[tuple[Optional[str], dict[str, Any]]] = []
    for item in items:
        tag = item.get("chapter_tag") or suggest_tag(item, taxonomy)
        tagged.append((tag, item))

    def _sort_key(tp: tuple[Optional[str], dict[str, Any]]) -> tuple:
        tag, item = tp
        tag_idx = tag_order.get(tag or "", 9999)
        is_stale = 1 if item.get("stale") is True else 0
        match_pct = float(item.get("match_percentage") or 0.0)
        recency = float(item.get("recency_bonus") or 0.0)
        composite = match_pct + recency
        title = item.get("title") or ""
        return (tag_idx, is_stale, -composite, title)

    tagged.sort(key=_sort_key)

    # Grouped overview.
    print_overview(tagged, taxonomy)
    print()
    try:
        input("  Press Enter to begin reviewing (Ctrl-C to quit without saving)... ")
    except KeyboardInterrupt:
        print("\n  Interrupted — nothing saved.")
        return [], [], items

    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    skipped:  list[dict[str, Any]] = []

    i = 0
    while i < len(tagged):
        suggested_tag, original_item = tagged[i]
        working = dict(original_item)
        working.setdefault("chapter_tag", suggested_tag)

        print_item(working, i + 1, len(tagged))

        # ── Action menu ──────────────────────────────────────────────────────
        acted = False
        while not acted:
            current_tag = working.get("chapter_tag") or "(untagged)"
            print()
            print("  [A] Approve   (chapter tag: {})".format(current_tag))
            print("  [E] Edit      (title / description / tag / note)")
            print("  [R] Reject    (remove from pending, do not store)")
            print("  [S] Skip      (leave in pending for next session)")
            print("  [B] Batch-approve all remaining items with auto-suggested tags")
            print("  [Q] Quit      (discard all choices made so far, exit now)")
            print()

            try:
                choice = input("  Choice [A/E/R/S/B/Q]: ").strip().upper()
            except KeyboardInterrupt:
                print("\n\n  Interrupted — discarding all choices, exiting.")
                return [], [], items

            if choice == "A":
                if not working.get("chapter_tag"):
                    print("  (!) A chapter tag is required before approving.")
                    print("      Press [E] to edit the item and assign a tag.")
                    continue
                approved.append(working)
                i += 1
                acted = True

            elif choice == "E":
                edit_dialog(working, taxonomy)
                # Re-display the updated item before re-showing the menu.
                print_item(working, i + 1, len(tagged))

            elif choice == "R":
                try:
                    confirm = input(
                        "  Confirm reject? This item will NOT be stored. [y/N]: "
                    ).strip().lower()
                except KeyboardInterrupt:
                    print()
                    continue
                if confirm == "y":
                    rejected.append(working)
                    i += 1
                    acted = True

            elif choice == "S":
                skipped.append(original_item)   # keep the original, unedited item
                i += 1
                acted = True

            elif choice == "B":
                try:
                    confirm = input(
                        "  Batch-approve ALL remaining items with auto-suggested tags? [y/N]: "
                    ).strip().lower()
                except KeyboardInterrupt:
                    print()
                    continue
                if confirm == "y":
                    # Include the current item (with any edits made so far).
                    if not working.get("chapter_tag"):
                        working["chapter_tag"] = suggested_tag or "emerging_topics"
                    approved.append(working)
                    # Approve all items not yet reached in the loop.
                    for rem_tag, rem_item in tagged[i + 1:]:
                        rem = dict(rem_item)
                        rem["chapter_tag"] = rem_tag or "emerging_topics"
                        approved.append(rem)
                    n_batch = len(tagged) - i
                    print("  Batch-approved {} item(s).".format(n_batch))
                    i = len(tagged)   # exit outer while
                    acted = True

            elif choice == "Q":
                try:
                    confirm = input(
                        "  Quit? ALL choices made this session will be discarded. [y/N]: "
                    ).strip().lower()
                except KeyboardInterrupt:
                    print()
                    continue
                if confirm == "y":
                    print("  Quit — nothing written. All items remain in pending.")
                    # Return all original items as skipped so nothing is lost.
                    return [], [], items

            else:
                print("  Invalid choice — enter A, E, R, S, B, or Q.")

    return approved, rejected, skipped


# ─────────────────────────────────────────────────────────────────────────────
# Pre-commit summary
# ─────────────────────────────────────────────────────────────────────────────


def print_pre_commit_summary(
    approved: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    skipped:  list[dict[str, Any]],
    db_path:  Path,
) -> None:
    _section("Pre-Commit Summary")
    print("  Approved : {:>3} item(s)  ->  will be WRITTEN to {}".format(len(approved), db_path.name))
    print("  Rejected : {:>3} item(s)  ->  will be REMOVED from pending_items.jsonl".format(len(rejected)))
    print("  Skipped  : {:>3} item(s)  ->  will REMAIN in pending_items.jsonl".format(len(skipped)))

    if approved:
        print()
        print("  Items to commit ({} total):".format(len(approved)))
        for n, item in enumerate(approved, 1):
            tag   = item.get("chapter_tag") or "(untagged)"
            title = _trunc(item.get("title") or "(no title)", 46)
            print("  {:>3}. [{:<30}]  {}".format(n, tag, title))


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation gate
# ─────────────────────────────────────────────────────────────────────────────


def request_confirmation(
    approved: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    db_path:  Path,
) -> bool:
    """
    Display the explicit write-confirmation prompt.

    Returns True ONLY when the reviewer types exactly the word CONFIRM.
    Any other input — including pressing Enter alone — returns False and
    aborts the write.  This is the sole gate guarding all disk writes.
    """
    print()
    print("=" * _W)
    print("  FINAL CONFIRMATION REQUIRED")
    print("=" * _W)
    print()
    print("  You are about to permanently commit {} approved item(s) to:".format(len(approved)))
    print("    {}".format(db_path))
    print()
    print("  This operation is IRREVERSIBLE.")
    print("  Records are appended to knowledge_store.db and are never overwritten.")
    if rejected:
        print("  {} rejected item(s) will be deleted from pending_items.jsonl.".format(len(rejected)))
    print("  Skipped items will remain in pending_items.jsonl for the next session.")
    print()
    print("  To proceed, type exactly:  CONFIRM")
    print("  To abort without saving:   press Enter  (or type anything else)")
    print()

    try:
        response = input("  > ").strip()
    except KeyboardInterrupt:
        print()
        return False

    return response == "CONFIRM"


# ─────────────────────────────────────────────────────────────────────────────
# Write to DB (append-only)
# ─────────────────────────────────────────────────────────────────────────────


def write_approved(
    approved: list[dict[str, Any]],
    run_id:   str,
    conn:     sqlite3.Connection,
    reviewer: str = "human_reviewer",
) -> int:
    """
    Append all *approved* items to knowledge_store.db in a single atomic
    transaction.

    APPEND-ONLY CONTRACT: this function NEVER calls UPDATE or DELETE on
    knowledge_items.  The UNIQUE constraint on pending_id ensures that
    re-committing an already-stored item raises IntegrityError (handled below)
    rather than silently overwriting data.

    Returns the number of rows successfully inserted.
    """
    now      = datetime.now(timezone.utc).isoformat()
    inserted = 0

    tax_ver = "1.1"
    queries_ver = "1.1"
    try:
        if _DEFAULT_TAXONOMY.exists():
            tax_ver = json.loads(_DEFAULT_TAXONOMY.read_text(encoding="utf-8")).get("version", "1.1")
        queries_path = _ROOT / "config" / "literature_queries.json"
        if queries_path.exists():
            queries_ver = json.loads(queries_path.read_text(encoding="utf-8")).get("version", "1.1")
    except Exception:
        pass

    # Single transaction: all-or-nothing.
    with conn:
        for item in approved:
            item_data = dict(item)
            synth_method = item.get("synthesis_method", "gemini")
            if synth_method == "gemini":
                item_data["model_name"] = item.get("model_name") or item.get("synthesis_model") or "gemini-2.5-flash"
            else:
                item_data["model_name"] = None
            item_data.setdefault("config_versions", {
                "taxonomy_version": tax_ver,
                "queries_version": queries_ver,
            })
            item_data["reviewer"] = reviewer

            try:
                conn.execute(
                    """
                    INSERT INTO knowledge_items
                        (pending_id, run_id, source_type, chapter_tag,
                         title, description, metadata_json,
                         reviewer_note, reviewed_at, reviewer_action)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved')
                    """,
                    (
                        item["id"],
                        run_id,
                        item.get("source_type", "unknown"),
                        item.get("chapter_tag", "emerging_topics"),
                        item.get("title"),
                        item.get("description", ""),
                        # Full item with provenance metadata stored as JSON blob.
                        json.dumps(item_data, ensure_ascii=False),
                        item.get("reviewer_note"),
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # pending_id UNIQUE violation — item already committed.
                print("  WARNING: item {} already in knowledge_store.db — skipped.".format(
                    item.get("id", "?")))

    return inserted


def rewrite_pending(skipped: list[dict[str, Any]], path: Path) -> None:
    """
    Rewrite *path* (pending_items.jsonl) to contain only *skipped* items.

    Approved and rejected items are not included.  If *skipped* is empty the
    file is truncated to zero bytes but not deleted (so the path still exists).
    """
    content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in skipped)
    path.write_text(content, encoding="utf-8")


def append_rejected_log(
    rejected: list[dict[str, Any]],
    log_path: Path,
) -> int:
    """
    Append a minimal audit log entry for each rejected item to log_path.
    Schema: {"id": str, "title": str, "rejected_at": ISO_UTC_TIMESTAMP}
    """
    if not rejected:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        for item in rejected:
            entry = {
                "id":          item.get("id"),
                "title":       item.get("title"),
                "rejected_at": now,
            }
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(rejected)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_checkpoint",
        description=(
            "BioLitAgent Review Checkpoint — interactive human-in-the-loop review "
            "of pending items before they are committed to the knowledge store."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pending",       default=str(_DEFAULT_PENDING),      metavar="PATH",
                        help="Path to pending_items.jsonl.")
    parser.add_argument("--db",            default=str(_DEFAULT_DB),           metavar="PATH",
                        help="Path to knowledge_store.db (SQLite).")
    parser.add_argument("--taxonomy",      default=str(_DEFAULT_TAXONOMY),     metavar="PATH",
                        help="Path to chapter_taxonomy.json.")
    parser.add_argument("--rejected-log",  default=str(_DEFAULT_REJECTED_LOG), metavar="PATH",
                        help="Path to rejected_items_log.jsonl audit log.")
    default_reviewer = (
        os.environ.get("BIOLITAGENT_REVIEWER")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "human_reviewer"
    )
    parser.add_argument("--reviewer",      default=default_reviewer,           metavar="NAME",
                        help="Identifier of reviewer conducting this approval run.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args              = _build_parser().parse_args(argv)
    pending_path      = Path(args.pending)
    db_path           = Path(args.db)
    taxonomy_path     = Path(args.taxonomy)
    rejected_log_path = Path(args.rejected_log)
    reviewer          = getattr(args, "reviewer", "human_reviewer")

    # ── Load taxonomy ────────────────────────────────────────────────────────
    try:
        taxonomy = load_taxonomy(taxonomy_path)
    except (FileNotFoundError, ValueError) as exc:
        print("ERROR: {}".format(exc))
        return 1

    # ── Open DB + create run record ──────────────────────────────────────────
    conn   = open_db(db_path)
    run_id = str(uuid.uuid4())
    create_run_record(conn, run_id, reviewer=reviewer)

    # ── Load and filter pending items ────────────────────────────────────────
    all_pending = load_pending(pending_path)
    seen_ids    = already_approved_ids(conn)
    new_items   = [item for item in all_pending if item.get("id") not in seen_ids]
    n_already   = len(all_pending) - len(new_items)

    # ── Banner ───────────────────────────────────────────────────────────────
    _banner(run_id)
    last_ts = last_run_completed_at(conn)
    if last_ts:
        print("  Last approved run : {} UTC".format(last_ts[:19].replace("T", " ")))
    else:
        print("  First run — no previous approval sessions in this knowledge store.")
    print("  Reviewer          : {}".format(reviewer))
    print("  Pending items     : {} total".format(len(all_pending)))
    if n_already:
        print("  Already committed : {} (filtered out — already in knowledge store)".format(n_already))
    print("  New to review     : {}".format(len(new_items)))
    print("  Knowledge store   : {}".format(db_path))

    if not new_items:
        print()
        print("  Nothing new to review.  Exiting.")
        update_run_record(conn, run_id, 0, 0, 0, reviewer=reviewer)
        conn.close()
        return 0

    # ── Interactive review ───────────────────────────────────────────────────
    try:
        approved, rejected, skipped = review_items(new_items, taxonomy)
    except KeyboardInterrupt:
        print("\n\n  Interrupted — nothing written.")
        update_run_record(conn, run_id, 0, 0, len(new_items), reviewer=reviewer)
        conn.close()
        return 1

    # ── Pre-commit summary ───────────────────────────────────────────────────
    print_pre_commit_summary(approved, rejected, skipped, db_path)

    if not approved and not rejected:
        print()
        print("  Nothing to commit or remove — pending_items.jsonl is unchanged.")
        update_run_record(conn, run_id, 0, 0, len(skipped), reviewer=reviewer)
        conn.close()
        return 0

    # ── Explicit confirmation gate (the only write path) ─────────────────────
    if not request_confirmation(approved, rejected, db_path):
        print()
        print("  Aborted.  Nothing written.  All items remain in pending_items.jsonl.")
        update_run_record(conn, run_id, 0, 0, len(new_items), reviewer=reviewer)
        conn.close()
        return 0

    # ── Write approved items → DB ─────────────────────────────────────────────
    inserted = write_approved(approved, run_id, conn, reviewer=reviewer)
    print("  Wrote {} item(s) to {}.".format(inserted, db_path.name))

    # ── Rewrite pending (keep only skipped) ──────────────────────────────────
    rewrite_pending(skipped, pending_path)
    print("  Rewrote {}: {} skipped item(s) remain.".format(pending_path.name, len(skipped)))

    # ── Audit log rejected items ─────────────────────────────────────────────
    if rejected:
        n_logged = append_rejected_log(rejected, rejected_log_path)
        print("  Logged {} rejected item(s) to {}.".format(n_logged, rejected_log_path.name))

    # ── Close run record ─────────────────────────────────────────────────────
    update_run_record(conn, run_id, inserted, len(rejected), len(skipped), reviewer=reviewer)
    conn.close()

    print()
    print("=" * _W)
    print("  Review complete.  Committed: {}   Rejected: {}   Skipped: {}".format(
        inserted, len(rejected), len(skipped)))
    print("=" * _W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
