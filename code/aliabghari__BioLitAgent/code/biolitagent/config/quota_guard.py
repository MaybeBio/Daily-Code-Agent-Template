"""
config/quota_guard.py
---------------------
Shared, persistent Gemini API quota management and pre-flight gate for BioLitAgent.
Maintains daily call counts across all agents in storage/quota_usage.json,
identifies daily vs. per-minute quota exhaustion, and provides pre-flight
cost estimation gates.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import time
from contextlib import contextmanager

log = logging.getLogger("quota_guard")

# Default daily limit on Google Gemini free tier (gemini-2.5-flash)
DEFAULT_DAILY_LIMIT = 20
SAFETY_MARGIN = 2

# Resolve paths
_ROOT = Path(__file__).resolve().parent.parent
_USAGE_FILE = _ROOT / "storage" / "quota_usage.json"
_LOCK_FILE = _ROOT / "storage" / ".quota_guard.lock"
_LOCK_TIMEOUT_SECONDS = 90.0
_LOCK_POLL_INTERVAL = 0.5


@contextmanager
def _orchestration_stdin_lock(agent_name: str):
    """
    Acquire a file-based lock before reading interactive stdin when running
    as an orchestrated subprocess under run_all.py. Ensures concurrent agents
    take turns at the confirmation prompt.
    """
    is_orchestrated = os.environ.get("BIOLITAGENT_ORCHESTRATED") == "1"
    if not is_orchestrated:
        yield
        return

    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    lock_fd = None
    waited = False

    while True:
        try:
            # Atomic creation: fails with FileExistsError if another agent holds it
            lock_fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, f"agent={agent_name} pid={os.getpid()} ts={time.time()}\n".encode("utf-8"))
            break
        except FileExistsError:
            try:
                mtime = _LOCK_FILE.stat().st_mtime
                if (time.time() - mtime) > _LOCK_TIMEOUT_SECONDS:
                    log.warning("Found stale quota guard lockfile (%s) -- breaking stale lock.", _LOCK_FILE)
                    try:
                        _LOCK_FILE.unlink()
                    except OSError:
                        pass
                    continue
            except OSError:
                pass

            if not waited:
                log.info(
                    "  [QUOTA GUARD] [%s] Another agent is currently at the confirmation prompt; waiting turn...",
                    agent_name,
                )
                waited = True
            time.sleep(_LOCK_POLL_INTERVAL)

            if (time.time() - start_time) > _LOCK_TIMEOUT_SECONDS:
                log.warning(
                    "  [QUOTA GUARD] [%s] Timed out waiting for stdin lock after %.0fs; proceeding anyway.",
                    agent_name,
                    _LOCK_TIMEOUT_SECONDS,
                )
                break

    try:
        yield
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                if _LOCK_FILE.exists():
                    _LOCK_FILE.unlink()
            except OSError:
                pass


def _today_utc() -> str:
    """Return current date in YYYY-MM-DD UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_usage_today() -> dict[str, Any]:
    """
    Retrieve today's quota usage, resetting counters if stored date != today's UTC date.
    Returns:
      {
        "date": "YYYY-MM-DD",
        "calls_made": int,
        "calls_by_agent": {
          "literature_scout": int,
          "regulatory_watch": int,
          ...
        }
      }
    """
    today = _today_utc()
    default_state = {
        "date": today,
        "calls_made": 0,
        "calls_by_agent": {
            "literature_scout": 0,
            "regulatory_watch": 0,
            "pdf_ingestion": 0,
        },
    }

    if not _USAGE_FILE.exists():
        save_usage(default_state)
        return default_state

    try:
        data = json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
        if data.get("date") != today:
            # New calendar day in UTC -- reset to zero
            log.info("Resetting daily quota usage tracker for new date: %s", today)
            save_usage(default_state)
            return default_state
        return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read quota_usage.json (%s) -- resetting state.", exc)
        save_usage(default_state)
        return default_state


def save_usage(data: dict[str, Any]) -> None:
    """Persist quota usage state to storage/quota_usage.json."""
    try:
        _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _USAGE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("Could not write to %s: %s", _USAGE_FILE, exc)


def record_call(agent_name: str) -> int:
    """
    Increment calls_made and calls_by_agent[agent_name] immediately after every
    real Gemini API attempt (success OR failure).
    Returns the new calls_made count for today.
    """
    state = get_usage_today()
    state["calls_made"] = state.get("calls_made", 0) + 1
    by_agent = state.setdefault("calls_by_agent", {})
    by_agent[agent_name] = by_agent.get(agent_name, 0) + 1
    save_usage(state)
    return state["calls_made"]


def parse_quota_failure(exc: Exception) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Inspect an API exception to determine if it is a quota failure,
    extracting (is_quota_failure, quota_id, duration_retry_str).
    
    Checks both structured exception attributes and stringified JSON.
    Returns:
      (is_quota_exhausted: bool, quota_id: Optional[str], retry_delay: Optional[str])
    """
    exc_str = str(exc)
    if "429" not in exc_str and "RESOURCE_EXHAUSTED" not in exc_str:
        return False, None, None

    quota_id = None
    retry_delay = None

    # Check for structured details in Google GenAI API errors
    # e.g., exc.response.json() or error details dictionary
    details = getattr(exc, "details", None)
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                violations = item.get("violations", [])
                for v in violations:
                    if isinstance(v, dict) and "quotaId" in v:
                        quota_id = v["quotaId"]
                if "retryDelay" in item:
                    retry_delay = str(item["retryDelay"])

    # Regex search for quotaId if not found in attributes
    if not quota_id:
        match_id = re.search(r"['\"]quotaId['\"]\s*:\s*['\"]([^'\"]+)['\"]", exc_str)
        if match_id:
            quota_id = match_id.group(1)

    # Search for retryDelay
    if not retry_delay:
        match_delay = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"]([^'\"]+)['\"]", exc_str)
        if match_delay:
            retry_delay = match_delay.group(1)

    return True, quota_id, retry_delay


def is_daily_exhaustion(quota_id: Optional[str], exc_str: str = "") -> bool:
    """
    Determine if a quota exhaustion is a per-day limit (non-retryable within run)
    vs a transient per-minute rate limit.
    """
    if quota_id:
        if any(term in quota_id for term in ("PerDay", "per_day", "perday", "daily")):
            return True
        if any(term in quota_id for term in ("PerMinute", "per_minute", "perminute")):
            return False

    # Fallback to string matching on violation description
    if "PerDay" in exc_str or "requests per day" in exc_str.lower():
        return True

    return False


def check_preflight_gate(estimated_calls: int, agent_name: str) -> bool:
    """
    Pre-flight estimate and confirmation gate.
    If estimated_calls <= (remaining_quota - SAFETY_MARGIN):
        Proceeds automatically (returns True).
    If estimated_calls would exceed or eat into remaining quota:
        Prompts user for explicit 'CONTINUE' confirmation.
        Returns True if user types 'CONTINUE', False on abort.
    """
    # If pre-flight confirmation was already given at the manager/pipeline level, proceed
    if os.environ.get("BIOLITAGENT_PREFLIGHT_CONFIRMED") == "1":
        return True

    usage = get_usage_today()
    calls_made = usage.get("calls_made", 0)
    remaining = max(0, DEFAULT_DAILY_LIMIT - calls_made)
    safe_threshold = max(0, remaining - SAFETY_MARGIN)

    # Normal healthy day with plenty of quota -- silent proceed
    if estimated_calls <= safe_threshold:
        return True

    # Quota is tight or will be exhausted
    with _orchestration_stdin_lock(agent_name):
        print()
        print("!" * 78)
        print(f"  [QUOTA GUARD] Pre-Flight Gate for {agent_name}")
        print("!" * 78)
        print(f"  This run needs an estimated {estimated_calls} fresh Gemini call(s).")
        print(f"  Quota used today: {calls_made}/{DEFAULT_DAILY_LIMIT} ({remaining} remaining).")
        if estimated_calls > remaining:
            print("  WARNING: This run EXCEEDS today's remaining quota and will encounter 429 errors.")
        else:
            print("  WARNING: Proceeding will consume nearly all remaining quota for today.")
        print()
        print("  Type CONTINUE to proceed anyway, or anything else to abort:")

        try:
            resp = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  [QUOTA GUARD] Aborted by user -- 0 API calls spent.")
            return False

        if resp == "CONTINUE":
            print("  [QUOTA GUARD] Confirmation received -- proceeding with API calls.")
            print(f"  [QUOTA GUARD] Proceeding despite low quota per explicit CONTINUE ({calls_made}/{DEFAULT_DAILY_LIMIT} used).")
            log.warning(
                "Proceeding despite low quota per explicit CONTINUE by reviewer (%d/%d used today).",
                calls_made,
                DEFAULT_DAILY_LIMIT,
            )
            return True

        print(f"  [QUOTA GUARD] Aborted by reviewer ('{resp}') -- no API calls were made.")
        return False


# Synchronize quota usage state on import so storage/quota_usage.json is truthful
try:
    get_usage_today()
except Exception:
    pass


if __name__ == "__main__":
    usage = get_usage_today()
    print(f"Current UTC date: {_today_utc()}")
    print(f"Quota usage file: {_USAGE_FILE}")
    print(f"Calls made today: {usage['calls_made']}/{DEFAULT_DAILY_LIMIT}")
    print(f"Calls by agent: {json.dumps(usage['calls_by_agent'], indent=2)}")
