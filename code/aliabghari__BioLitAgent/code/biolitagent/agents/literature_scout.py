#!/usr/bin/env python3
"""
agents/literature_scout.py
------------------------------------------------------------------------------
Literature Scout Agent for BioLitAgent.

Monitors biomedical and bioprocess preprint / peer-reviewed literature:
  1. Integrates with configured MCP servers (PubMed, bioRxiv per mcp_config.json)
     passing NCBI_EMAIL and NCBI_API_KEY to the MCP server's connection config,
     with robust exception handling for connection failures (timeout, connection
     refused, auth failure) and direct public API fallbacks.
  2. Tracks previously-seen items in storage/literature_state.json to prevent
     re-processing duplicates.
  3. Extracts metadata: title, authors, DOI, publication date.
  4. Generates a concise (2-3 sentence) original paraphrase of key findings
     via the Gemini API -- never copying verbatim abstract text.
  5. Implements retry-with-backoff for transient LLM API errors (429/503),
     inspecting the status code attribute on the exception object.
  6. Appends structured records to storage/pending_items.jsonl matching the
     regulatory_watch.py schema exactly:
       id, source_type, title, agency, url, url_unknown, publication_date,
       date_unknown, description, detected_at, content_hash, source_id, index_url

Usage
-----
  python agents/literature_scout.py
  python agents/literature_scout.py --limit 3
  python agents/literature_scout.py --dry-run
  python agents/literature_scout.py --queries config/literature_queries.json
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# -- Paths ---------------------------------------------------------------------
_ROOT              = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

_ENV_FILE          = _ROOT / ".env"
_DEFAULT_QUERIES   = _ROOT / "config" / "literature_queries.json"
_DEFAULT_STATE     = _ROOT / "storage" / "literature_state.json"
_OUTPUT_FILE       = _ROOT / "storage" / "pending_items.jsonl"
_MCP_CONFIG_FILE   = _ROOT / "mcp_config.json"
_DRY_RUN_CACHE_FILE = _ROOT / "storage" / "dry_run_llm_cache.json"
_FILTERED_LOG_FILE = _ROOT / "storage" / "filtered_items_log.jsonl"
_FILTER_PREVIEW_FILE = _ROOT / "storage" / "filter_preview.jsonl"

# -- Optional: python-dotenv ---------------------------------------------------
try:
    from dotenv import load_dotenv
    if _ENV_FILE.exists():
        load_dotenv(dotenv_path=_ENV_FILE, override=False)
    else:
        load_dotenv(override=False)
except ImportError:
    pass

# -- Optional: google-genai ----------------------------------------------------
try:
    import google.genai as genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# Matches regulatory_watch.py model via central model_config
try:
    from biolitagent.config.model_config import DEFAULT_MODEL
except ImportError:
    try:
        from config.model_config import DEFAULT_MODEL
    except ImportError:
        DEFAULT_MODEL = "gemini-2.5-flash"

_DEFAULT_MODEL = DEFAULT_MODEL

_RETRYABLE_STATUS_CODES = {429, 503}
_MAX_LLM_RETRIES = 3
_BACKOFF_BASE = 2.0  # 2s, 4s, 8s

_NCBI_ESEARCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_NCBI_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
_NCBI_EFETCH_URL   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_BIORXIV_API_URL   = "https://api.biorxiv.org/details/biorxiv"

# -- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("literature_scout")

_llm_client: Optional[Any] = None
_llm_model:  str           = _DEFAULT_MODEL
_llm_init_attempted: bool  = False
_daily_quota_exhausted: bool = False
_preflight_checked: bool = False

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


def get_google_api_key() -> Optional[str]:
    """
    Single source of truth for whether the Google Gemini API key is present.
    Checks environment variables (GOOGLE_API_KEY, GEMINI_API_KEY) and .env files.
    Returns the key string if present and non-empty, otherwise None.
    """
    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    # If not present in os.environ, check local .env files
    for env_path in (_ENV_FILE, _ROOT / ".env", Path.cwd() / ".env"):
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                vals = dotenv_values(env_path)
                for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                    k = (vals.get(var) or "").strip()
                    if k:
                        os.environ["GOOGLE_API_KEY"] = k
                        return k
            except Exception:
                pass

    return None


def _get_llm_client() -> Optional[Any]:
    """
    Return a cached google.genai Client, initializing it on first call.
    Uses get_google_api_key() as the single source of truth.
    Logs warning messages and fallback-mode triggers at most once per run.
    """
    global _llm_client, _llm_init_attempted
    if _llm_init_attempted:
        return _llm_client

    _llm_init_attempted = True

    if not _GENAI_AVAILABLE:
        log.warning("google-genai is not installed; running in fallback mode.")
        return None

    api_key = get_google_api_key()
    if not api_key:
        log.warning("GOOGLE_API_KEY is not set; running in fallback mode.")
        return None

    try:
        _llm_client = genai.Client(api_key=api_key)
        log.debug("Gemini client initialised (model: %s).", _llm_model)
    except Exception as exc:
        log.warning("Could not initialise Gemini client: %s; running in fallback mode.", exc)
        _llm_client = None

    return _llm_client


def reset_llm_client() -> None:
    """Reset cached LLM client and initialization state (used for testing or reconfiguration)."""
    global _llm_client, _llm_init_attempted
    _llm_client = None
    _llm_init_attempted = False


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


# -- State helpers -------------------------------------------------------------


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen_ids": {}, "last_run": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("Could not read %s -- starting with empty state.", path.name)
        return {"seen_ids": {}, "last_run": None}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# -- Dry-Run LLM Response Cache Helpers ----------------------------------------


def load_dry_run_cache() -> dict[str, Any]:
    """Load the dry-run LLM response cache from storage/dry_run_llm_cache.json."""
    if _DRY_RUN_CACHE_FILE.exists():
        try:
            return json.loads(_DRY_RUN_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read dry_run_llm_cache.json: %s", exc)
    return {}


def save_dry_run_cache(cache: dict[str, Any]) -> None:
    """Persist the dry-run LLM response cache to storage/dry_run_llm_cache.json."""
    try:
        _DRY_RUN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DRY_RUN_CACHE_FILE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        log.debug("Dry-run cache saved -> %s", _DRY_RUN_CACHE_FILE)
    except OSError as exc:
        log.warning("Could not save dry-run cache to %s: %s", _DRY_RUN_CACHE_FILE, exc)


def _compute_item_hash(item: dict[str, Any], query_id: str = "") -> str:
    """Compute a stable SHA-256 hash of query + candidate item content."""
    title = (item.get("title") or "").strip().lower()
    source_text = (item.get("source_text") or "").strip()[:1500]
    payload = f"{query_id}:{title}:{source_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_paraphrase(item_hash: str) -> Optional[tuple[str, str]]:
    """Retrieve (cached_paraphrase, synthesis_method) for item_hash from storage/dry_run_llm_cache.json."""
    cache = load_dry_run_cache()
    entry = cache.get(item_hash)
    if not entry or not isinstance(entry, dict):
        return None
    method = entry.get("synthesis_method", "gemini")
    if "paraphrase" in entry and entry["paraphrase"]:
        return str(entry["paraphrase"]), method
    items = entry.get("items", [])
    if items and isinstance(items, list) and isinstance(items[0], dict):
        desc = items[0].get("description")
        if desc:
            return str(desc), method
    return None


def cache_paraphrase(
    item_hash: str,
    query_id: str,
    title: str,
    paraphrase: str,
    synthesis_method: str = "gemini",
) -> None:
    """Store a paraphrase in storage/dry_run_llm_cache.json."""
    if not paraphrase:
        return
    cache = load_dry_run_cache()
    cache[item_hash] = {
        "source_id": query_id or "literature",
        "status": "ITEMS_FOUND",
        "paraphrase": paraphrase,
        "synthesis_method": synthesis_method,
        "items": [{"title": title, "description": paraphrase}],
        "detail": "Cached literature paraphrase",
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    save_dry_run_cache(cache)


# -- Rate limiting & Key validation -------------------------------------------
_last_ncbi_request_time: float = 0.0


def is_valid_ncbi_api_key(key: Optional[str]) -> bool:
    """Return True if NCBI_API_KEY is non-empty and not a placeholder."""
    if not key or not str(key).strip():
        return False
    k = str(key).strip().lower()
    return not any(p in k for p in ("your", "placeholder", "free_key"))


def is_valid_ncbi_email(email: Optional[str]) -> bool:
    """Return True if NCBI_EMAIL is non-empty and not a placeholder."""
    if not email or not str(email).strip():
        return False
    e = str(email).strip().lower()
    return not any(p in e for p in ("your", "placeholder", "example.com"))


def _rate_limit_ncbi() -> None:
    """
    Enforce rate limits on NCBI requests:
      - 0.12s interval with a valid NCBI_API_KEY (~8.3 req/s <= 10 req/s cap)
      - 0.40s interval without a key (~2.5 req/s <= 3 req/s cap)
    """
    global _last_ncbi_request_time
    has_key = is_valid_ncbi_api_key(os.environ.get("NCBI_API_KEY"))
    min_interval = 0.12 if has_key else 0.40
    now = time.time()
    elapsed = now - _last_ncbi_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_ncbi_request_time = time.time()


# -- MCP Server Integration & Distinct Failure Handling ------------------------


def get_mcp_server_config(server_name: str) -> Optional[dict[str, Any]]:
    """
    Load mcp_config.json, resolve the server configuration, and inject active
    environment variables (including NCBI_EMAIL and NCBI_API_KEY) into the
    server's runtime execution environment.
    """
    if not _MCP_CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(_MCP_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not read mcp_config.json: %s", exc)
        return None

    servers = data.get("mcpServers", {})
    if server_name not in servers:
        return None

    cfg = dict(servers[server_name])
    runtime_env = os.environ.copy()

    # Pass credentials explicitly to MCP server runtime env
    ncbi_email = os.environ.get("NCBI_EMAIL", "").strip()
    ncbi_api_key = os.environ.get("NCBI_API_KEY", "").strip()

    if ncbi_email:
        runtime_env["NCBI_EMAIL"] = ncbi_email
    if ncbi_api_key:
        runtime_env["NCBI_API_KEY"] = ncbi_api_key

    # Resolve any placeholder expansion in server config env
    for k, v in cfg.get("env", {}).items():
        val = str(v)
        if val.startswith("${") and val.endswith("}"):
            vname = val[2:-1]
            val = os.environ.get(vname, "")
        if val:
            runtime_env[k] = val

    cfg["runtime_env"] = runtime_env
    return cfg


def check_mcp_server_connection(server_name: str, timeout_sec: float = 5.0) -> tuple[bool, str]:
    """
    Verify MCP server readiness according to mcp_config.json and injected credentials.
    Explicitly distinguishes and logs:
      - [MCP_AUTH_FAILURE]: Missing required NCBI_EMAIL credentials
      - [MCP_CONNECTION_REFUSED]: npx/node process spawn error or command failure
      - [MCP_TIMEOUT]: Subprocess probe timeout
      - [MCP_PROBE_OK]: Successful connection & credential handshake
    """
    cfg = get_mcp_server_config(server_name)
    if not cfg:
        log.info("  [MCP_CONFIG_ABSENT] Server '%s' configuration not available in mcp_config.json.", server_name)
        return False, "CONFIG_ABSENT"

    command = cfg.get("command", "npx")
    runtime_env = cfg.get("runtime_env", {})

    # -- 1. Check Authentication requirements ---------------------------------
    if server_name == "pubmed":
        ncbi_email = runtime_env.get("NCBI_EMAIL", "").strip()
        if not is_valid_ncbi_email(ncbi_email):
            msg = "NCBI_EMAIL environment variable is missing or placeholder (required by NCBI fair-use policy)"
            log.warning("  [MCP_AUTH_FAILURE] Authentication check failed for MCP server '%s': %s", server_name, msg)
            return False, "AUTH_FAILURE"

    # -- 2. Probe subprocess invocation with timeout ---------------------------
    resolved_cmd = shutil.which(command) or (f"{command}.cmd" if sys.platform.startswith("win") else command)
    probe_cmd = [resolved_cmd, "--version"]

    try:
        proc = subprocess.run(
            probe_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            env=runtime_env,
            shell=sys.platform.startswith("win"),
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            log.warning("  [MCP_CONNECTION_REFUSED] Connection failed for MCP server '%s' (exit code %d): %s",
                        server_name, proc.returncode, err)
            return False, "CONNECTION_REFUSED"

        version_info = proc.stdout.decode("utf-8", errors="replace").strip()
        auth_notes = [f"NCBI_EMAIL={runtime_env.get('NCBI_EMAIL')}"]
        if is_valid_ncbi_api_key(runtime_env.get("NCBI_API_KEY")):
            auth_notes.append("NCBI_API_KEY=configured")
        else:
            auth_notes.append("NCBI_API_KEY=missing (unauthenticated, ~3 req/s)")
        auth_note = ", ".join(auth_notes)
        log.info("  [MCP_PROBE_OK] Successfully probed MCP server '%s' (transport: %s, %s v%s, auth: %s)",
                 server_name, cfg.get("transport", "stdio"), command, version_info, auth_note)
        return True, "READY"

    except subprocess.TimeoutExpired:
        log.warning("  [MCP_TIMEOUT] Connection timed out after %.1fs for MCP server '%s'.", timeout_sec, server_name)
        return False, "TIMEOUT"

    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        log.warning("  [MCP_CONNECTION_REFUSED] Failed to spawn MCP server '%s' (%s: %s).", server_name, type(exc).__name__, exc)
        return False, "CONNECTION_REFUSED"

    except Exception as exc:
        log.warning("  [MCP_CONNECTION_REFUSED] Unexpected error connecting to MCP server '%s': %s", server_name, exc)
        return False, "CONNECTION_REFUSED"


# -- Network helpers (Direct REST Fallback) ------------------------------------


class NetworkFetchError(Exception):
    """Raised when an HTTP request fails after retries or encounters non-retryable errors."""
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
        is_rate_limited: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.is_rate_limited = is_rate_limited


def _http_get_bytes(
    url: str,
    params: dict[str, str],
    timeout: float = 15.0,
    max_retries: int = 3,
) -> bytes:
    """
    Issue an HTTP GET request with retries, exponential backoff, rate limiting,
    and honors Retry-After headers when present. Returns raw response bytes.
    """
    if "ncbi.nlm.nih.gov" in url:
        _rate_limit_ncbi()

    full_url = url + "?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": "BioLitAgent/1.0 (Bioprocess Literature Monitor; mailto:biolitagent@example.com)",
        "Accept": "application/xml, application/json, text/plain",
    }
    req = urllib.request.Request(full_url, headers=headers)

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            status_code = exc.code
            retry_after: Optional[float] = None
            raw_ra = exc.headers.get("Retry-After") if exc.headers else None
            if raw_ra:
                try:
                    retry_after = float(raw_ra)
                except ValueError:
                    pass

            is_rate_limit = (status_code == 429)
            if (is_rate_limit or 500 <= status_code < 600) and attempt < max_retries - 1:
                delay = retry_after if retry_after is not None else (1.5 * (2 ** attempt))
                log.warning(
                    "  [HTTP_RETRY %d/%d] HTTP %d from %s (retrying in %.1fs): %s",
                    attempt + 1, max_retries, status_code, url, delay, exc,
                )
                time.sleep(delay)
                continue

            raise NetworkFetchError(
                f"HTTP {status_code} error fetching {url}: {exc}",
                status_code=status_code,
                retry_after=retry_after,
                is_rate_limited=is_rate_limit,
            ) from exc

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = 1.5 * (2 ** attempt)
                log.warning(
                    "  [HTTP_RETRY %d/%d] Network error from %s (retrying in %.1fs): %s",
                    attempt + 1, max_retries, url, delay, exc,
                )
                time.sleep(delay)
                continue
            raise NetworkFetchError(f"Network error fetching {url}: {exc}") from exc

    raise NetworkFetchError(f"Failed to fetch {url} after {max_retries} attempts: {last_exc}")


def _http_get_json(
    url: str,
    params: dict[str, str],
    timeout: float = 15.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Issue a GET request returning parsed JSON, using _http_get_bytes."""
    data = _http_get_bytes(url, params, timeout=timeout, max_retries=max_retries)
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise NetworkFetchError(f"Invalid JSON returned from {url}: {exc}") from exc


# -- PubMed Search & Fetch via E-utilities --------------------------------------


def search_pubmed(
    query: str,
    limit: int = 5,
    sort: str = "pub_date",
    pub_window_years: Optional[int] = 3,
) -> list[str]:
    """Search PubMed using esearch and return up to *limit* PMIDs within publication window."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(limit),
        "sort": sort,
    }
    if pub_window_years is not None and pub_window_years > 0:
        now_yr = datetime.now(timezone.utc).year
        params["mindate"] = f"{now_yr - pub_window_years}/01/01"
        params["maxdate"] = f"{now_yr}/12/31"
        params["datetype"] = "pdat"

    raw_key = os.environ.get("NCBI_API_KEY", "").strip()
    if is_valid_ncbi_api_key(raw_key):
        params["api_key"] = raw_key
    raw_email = os.environ.get("NCBI_EMAIL", "").strip()
    if is_valid_ncbi_email(raw_email):
        params["email"] = raw_email

    res = _http_get_json(_NCBI_ESEARCH_URL, params)
    return res.get("esearchresult", {}).get("idlist", [])


def fetch_pubmed_abstracts(pmids: list[str]) -> dict[str, str]:
    """
    Fetch abstracts for a list of PMIDs using ONE batched efetch call (XML).
    Respects NCBI rate limiting and retries.
    Returns {pmid: abstract_text}.
    """
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    raw_key = os.environ.get("NCBI_API_KEY", "").strip()
    if is_valid_ncbi_api_key(raw_key):
        params["api_key"] = raw_key
    raw_email = os.environ.get("NCBI_EMAIL", "").strip()
    if is_valid_ncbi_email(raw_email):
        params["email"] = raw_email

    abstracts: dict[str, str] = {p: "" for p in pmids}
    try:
        xml_data = _http_get_bytes(_NCBI_EFETCH_URL, params)
        root = ET.fromstring(xml_data)
        for article in root.findall(".//PubmedArticle"):
            pmid_elem = article.find(".//MedlineCitation/PMID")
            if pmid_elem is None or not pmid_elem.text:
                continue
            pmid = pmid_elem.text.strip()
            abstract_elems = article.findall(".//MedlineCitation/Article/Abstract/AbstractText")
            if abstract_elems:
                parts = []
                for elem in abstract_elems:
                    lbl = elem.get("Label")
                    txt = "".join(elem.itertext()).strip()
                    if lbl and txt:
                        parts.append(f"{lbl}: {txt}")
                    elif txt:
                        parts.append(txt)
                abstracts[pmid] = " ".join(parts).strip()
    except Exception as exc:
        log.warning("Could not fetch/parse efetch XML for abstracts: %s", exc)
    return abstracts


def fetch_pubmed_summaries(pmids: list[str]) -> list[dict[str, Any]]:
    """Fetch article summary records for a list of PMIDs via esummary."""
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    raw_key = os.environ.get("NCBI_API_KEY", "").strip()
    if is_valid_ncbi_api_key(raw_key):
        params["api_key"] = raw_key
    raw_email = os.environ.get("NCBI_EMAIL", "").strip()
    if is_valid_ncbi_email(raw_email):
        params["email"] = raw_email

    res = _http_get_json(_NCBI_ESUMMARY_URL, params)
    result_dict = res.get("result", {})
    records = []
    for pmid in pmids:
        doc = result_dict.get(pmid)
        if not doc or not isinstance(doc, dict):
            continue

        title = doc.get("title", "").rstrip(".")
        authors = [a.get("name", "") for a in doc.get("authors", []) if a.get("name")]

        # Extract publication date / year
        pubdate = doc.get("pubdate", "")
        pub_date_formatted = None
        m_date = re.search(r"\b(19\d\d|20\d\d)(?:[-/ ](\d{1,2}))?(?:[-/ ](\d{1,2}))?\b", pubdate)
        if m_date:
            yr = m_date.group(1)
            mo = m_date.group(2) if m_date.group(2) else "01"
            da = m_date.group(3) if m_date.group(3) else "01"
            pub_date_formatted = f"{yr}-{int(mo):02d}-{int(da):02d}"
        else:
            pub_date_formatted = pubdate if pubdate else None

        # Extract DOI
        doi = None
        for aid in doc.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value")
                break

        records.append({
            "source": "pubmed",
            "agency": "PubMed",
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "publication_date": pub_date_formatted,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source_text": title,
        })
    return records


# -- bioRxiv Search via Public API ---------------------------------------------


def fetch_biorxiv_recent(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch recent preprints from bioRxiv API."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"{_BIORXIV_API_URL}/{today}/{today}/0/json"
    headers = {
        "User-Agent": "BioLitAgent/1.0 (mailto:biolitagent@example.com)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("bioRxiv fetch failed: %s", exc)
        return []

    collection = data.get("collection", [])
    records = []
    for item in collection[:limit]:
        title = item.get("biorxiv_title", "").rstrip(".")
        authors_raw = item.get("biorxiv_author_name", "")
        authors = [a.strip() for a in authors_raw.split(";") if a.strip()]
        doi = item.get("biorxiv_doi")
        date_str = item.get("biorxiv_date", "")

        abstract = item.get("biorxiv_abstract", "")

        records.append({
            "source": "biorxiv",
            "agency": "bioRxiv",
            "title": title,
            "authors": authors,
            "publication_date": date_str if date_str else None,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else "https://www.biorxiv.org",
            "source_text": abstract[:2000] if abstract else title,
        })
    return records


# -- Bioprocess Relevance Evaluation & Off-Topic Filtering -------------------

# Bioprocess Anchor Keywords (domain-specific, defining bioprocess engineering)
_BIOPROCESS_ANCHOR_KEYWORDS: dict[str, int] = {
    # Host platforms & cell lines
    "cho cells": 2, "chinese hamster ovary": 2, "cho cell": 2, "hek293": 2, "pichia": 2,
    "mammalian cell": 2, "suspension culture": 2, "suspension cell": 2,
    # Upstream unit operations & kinetics
    "perfusion": 2, "fed-batch": 2, "continuous bioprocess": 2, "continuous manufacturing": 2,
    "bioreactor": 2, "stirred-tank": 2, "wave bioreactor": 2, "viable cell density": 2,
    "volumetric productivity": 2, "specific productivity": 2,
    "seed train": 2, "n-1 perfusion": 2,
    # Downstream unit operations & purification
    "protein a": 2, "affinity chromatography": 2, "ion-exchange": 2,
    "hydrophobic interaction": 2, "tangential flow": 2, "tff": 2,
    "ultrafiltration": 2, "diafiltration": 2, "viral clearance": 2, "virus clearance": 2,
    "downstream process": 2, "multi-column": 2, "multimodal chromatography": 2,
    # Target molecules & CQAs
    "monoclonal antibody": 2, "mab": 2, "biopharmaceutical": 2, "biologic": 2,
    "recombinant protein": 2, "fusion protein": 2, "critical quality attribute": 2, "cqa": 2,
    "glycosylation": 2, "charge variant": 2, "multi-attribute method": 2,
    "quality by design": 2, "qbd": 2, "glycoprofiling": 2, "n-glycan": 2,
    "therapeutic protein": 2, "biotherapeutic": 2,
    # Digital bioprocess & advanced modalities
    "digital twin": 2, "hybrid model": 2, "hybrid modeling": 2, "mechanistic model": 2,
    "soft sensor": 2, "model-based bioprocess": 2,
    "lipid nanoparticle": 2, "lnp": 2, "in vitro transcription": 2, "ivt mrna": 2,
    # Microbiome & commensal platforms / live biotherapeutics
    "live biotherapeutic": 3, "lbp": 2, "commensal vaccine": 3, "engineered probiotic": 3,
    "microbial consortia": 2, "commensal": 2,
    "lyophilization": 2, "bacteroides": 2, "lactococcus": 2, "nissle": 2, "engineered bacteria": 2,
    # Microbial & bacterial expression anchors
    "inclusion body": 2, "signal peptide": 2, "codon optimization": 2,
    "soluble expression": 2, "protein solubility": 2, "refolding": 2,
    "solubility tag": 2, "fusion tag": 2, "chaperone": 2,
    # cGMP & early-phase manufacturing anchors
    "cgmp": 2, "gmp": 2, "good manufacturing practice": 2, "cmc": 2,
    "drug substance": 2, "drug product": 2, "phase-appropriate": 2,
    "investigational new drug": 2, "single-use": 2, "disposable": 2,
    "first-in-human": 2, "closed system": 2, "scale-out": 2,
    # Vaccine platforms (VLPs, OMVs, recombinant subunit vaccines)
    "vlp": 2, "virus-like particle": 2, "omv": 2, "outer membrane vesicle": 2,
    "recombinant subunit": 2, "vaccine manufacturing": 2, "vaccine production": 2,
    # General bioprocess anchors (weight 1 by default; raised to 2 ONLY when paired with a second anchor)
    "bioprocess": 1, "biomanufacturing": 1,
}

# Bioprocess Context Keywords (generic scientific terms, weight 1)
_BIOPROCESS_CONTEXT_KEYWORDS: dict[str, int] = {
    "elisa": 1,
    "flow cytometry": 1,
    "plasmid": 1,
    "e. coli": 1,
    "escherichia coli": 1,
    "endotoxin": 1,
    "sds-page": 1,
    "formulation": 1,
    "anaerobic": 1,
    "phase 1": 1,
    "purification": 1,
    "titer": 1,
    "release testing": 1,
    "cell viability": 1,
    "recombinant": 1,
    # Context-only per Requirement C:
    "microbiome": 1,
    "encapsulation": 1,
    "gut microbiota": 1,
}

# All positive bioprocess keywords (anchors + context)
_POSITIVE_BIOPROCESS_KEYWORDS: dict[str, int] = {
    **_BIOPROCESS_ANCHOR_KEYWORDS,
    **_BIOPROCESS_CONTEXT_KEYWORDS,
}

# Off-topic domain terms carrying severe negative penalties (-5 points each)
_NEGATIVE_OFF_TOPIC_KEYWORDS = {
    # Environmental / toxicology
    "zebrafish": 5, "ecotoxicology": 5, "ecotoxicological": 5, "acute toxicity": 5, "heavy metal": 5,
    "pesticide": 5, "wastewater": 5, "microplastic": 5, "lps-induced": 5,
    "toxicological": 5, "toxicology": 5,
    # Agriculture / food & beverage (never bare "food")
    "tea leaf": 5, "tea leaves": 5, "tea": 5, "wine": 5, "beer": 5,
    "brewing": 5, "soy sauce": 5, "food fermentation": 5, "cheese": 5,
    "dairy": 5, "sourdough": 5, "plant tissue": 5, "crop": 5,
    # Observational clinical cohort / non-bioprocess fecal studies
    "fecal microbiota transplantation": 5, "fecal transplant": 5, "fmt": 4,
    "dysbiosis cohort": 4, "fecal": 4,
    # Requirement C additions (word-boundary, phrase-level):
    "immunoadsorption": 5,
    "plaque assay": 5,
    "nebulizer": 5,
    "inhaler": 5,
    "traditional chinese medicine": 5,
    "soil": 5,
    "manure": 5,
    "compost": 5,
    "syngas": 5,
    "biogas": 5,
    "anaerobic digestion": 5,
    "daqu": 5,
    "liquor": 5,
    "coffee": 5,
    "cereal": 5,
    "skincare": 5,
    "cosmetic": 5,
    "nutraceutical": 5,
    "ethanol": 5,
    "biofuel": 5,
}

# Case-sensitive matching for CHO, CHO-K1, CHO-S
_CHO_CASE_SENSITIVE_PATTERN = re.compile(r"\bCHO(?:-(?:K1|S))?\b")

# "protein a" counts only if co-occurring with chromatography|resin|capture|affinity|purification
_PROTEIN_A_PATTERN = re.compile(r"\bprotein\s+a\b", re.IGNORECASE)
_PROTEIN_A_COOCCUR_PATTERN = re.compile(r"\b(?:chromatograph(?:y|ic|ically)?|resin|capture|affinity|purification)\b", re.IGNORECASE)

# Vaccine modality anchors count only if co-occurring with process/manufacturing terms
_VACCINE_MODALITY_KEYWORDS = {
    "vlp",
    "virus-like particle",
    "omv",
    "outer membrane vesicle",
    "recombinant subunit",
}
_VACCINE_PROCESS_COOCCUR_PATTERN = re.compile(
    r"\b(?:manufactur\w*|purification|chromatograph\w*|fermentation|titer|yield|bioprocess\w*|biomanufacturing|process\s+development|downstream|upstream|scale(?:-|\s*)(?:up|down))\b",
    re.IGNORECASE,
)

_ABSTRACT_SCORE_CAP = 6


def _build_keyword_regex(kw: str) -> re.Pattern[str]:
    """
    Build a regex pattern with word boundaries (\\b) and optional plural suffixes.
    Handles irregular plurals like 'body' -> 'bodies' and 'antibody' -> 'antibodies'.
    Prevents partial-word collisions (e.g. 'tea' matching 'steady' or 'instead').
    """
    kw_clean = kw.strip()
    kw_lower = kw_clean.lower()
    if kw_lower == "downstream process":
        return re.compile(r"\bdownstream\s+process(?:es|ing)?\b", re.IGNORECASE)
    if kw_lower == "glycoprofiling":
        return re.compile(r"\bglycoprofil\w*\b", re.IGNORECASE)
    if kw_lower == "n-glycan":
        return re.compile(r"\bn-glyc(?:an|ome)s?\b", re.IGNORECASE)
    if kw_lower == "multi-column":
        return re.compile(r"\bmulti(?:-|\s*)columns?\b", re.IGNORECASE)
    if kw_lower == "soft sensor":
        return re.compile(r"\bsoft(?:-|\s*)sensors?\b", re.IGNORECASE)
    if kw_lower == "model-based bioprocess":
        return re.compile(r"\bmodel(?:-|\s*)based\s+bioprocess(?:es|ing)?(?:\s+development)?\b", re.IGNORECASE)
    if kw_lower.endswith("body"):
        stem = kw_clean[:-4]
        pattern = r"\b" + re.escape(stem) + r"bod(?:y|ies)\b"
    elif kw_lower.endswith("antibody"):
        stem = kw_clean[:-8]
        pattern = r"\b" + re.escape(stem) + r"antibod(?:y|ies)\b"
    elif kw_clean.endswith("."):
        pattern = r"\b" + re.escape(kw_clean) + r"\b"
    elif kw_lower.endswith("ss") or kw_lower.endswith("sh") or kw_lower.endswith("ch") or kw_lower.endswith("x") or kw_lower.endswith("z"):
        pattern = r"\b" + re.escape(kw_clean) + r"(?:es)?\b"
    elif kw_lower.endswith("s"):
        pattern = r"\b" + re.escape(kw_clean) + r"\b"
    else:
        pattern = r"\b" + re.escape(kw_clean) + r"(?:s|es)?\b"
    return re.compile(pattern, re.IGNORECASE)


# Precompiled regex patterns with word boundaries and plural handling
_POSITIVE_BIOPROCESS_PATTERNS: dict[str, re.Pattern[str]] = {
    kw: _build_keyword_regex(kw) for kw in _POSITIVE_BIOPROCESS_KEYWORDS
}

_NEGATIVE_OFF_TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    kw: _build_keyword_regex(kw) for kw in _NEGATIVE_OFF_TOPIC_KEYWORDS
}


_RELEVANCE_SCORE_CEILING: float = 10.0


def calculate_recency_bonus(
    pub_date_or_year: Any,
    rolling_baseline_year: int = 2022,
) -> tuple[float, Optional[int]]:
    """
    Calculate soft continuous recency bonus (+0.5 per year newer than baseline, capped at +3.0).
    Returns (recency_bonus, publication_year).
    """
    year = None
    if pub_date_or_year is not None:
        if isinstance(pub_date_or_year, int):
            year = pub_date_or_year
        else:
            m = re.search(r"\b(19\d\d|20\d\d)\b", str(pub_date_or_year))
            if m:
                year = int(m.group(1))

    if year is None:
        return 0.0, None

    if year <= rolling_baseline_year:
        return 0.0, year

    bonus = min(3.0, (year - rolling_baseline_year) * 0.5)
    return round(bonus, 2), year


def check_7word_overlap(paraphrase: str, abstract_text: str) -> bool:
    """
    Return True if paraphrase shares 7 or more consecutive words with abstract_text
    (case-insensitive).
    """
    if not paraphrase or not abstract_text:
        return False
    para_words = re.findall(r"\b[A-Za-z0-9_-]+\b", paraphrase.lower())
    abstract_words = re.findall(r"\b[A-Za-z0-9_-]+\b", abstract_text.lower())
    if len(para_words) < 7 or len(abstract_words) < 7:
        return False

    abstract_7grams = set()
    for i in range(len(abstract_words) - 6):
        abstract_7grams.add(tuple(abstract_words[i:i + 7]))

    for i in range(len(para_words) - 6):
        if tuple(para_words[i:i + 7]) in abstract_7grams:
            return True
    return False


def evaluate_bioprocess_relevance(
    title: str,
    abstract_text: str = "",
    min_score: int = 2,
    score_ceiling: float = _RELEVANCE_SCORE_CEILING,
) -> tuple[bool, int, float, list[str], list[str]]:
    """
    Evaluate the bioprocess relevance of a literature candidate based on two-tier keywords:
      - Title is scored with 2x weight multiplier.
      - Abstract (if present) is scored with 1x weight multiplier, capped at _ABSTRACT_SCORE_CAP.
      - Anchor keywords: Domain-specific bioprocess engineering terms.
      - Context keywords: Generic scientific terms (weight 1).
      - "protein a" counts only if co-occurring with chromatography|resin|capture|affinity|purification.
      - "bioprocess" and "biomanufacturing" are raised to weight 2 ONLY when paired with a second anchor.
      - Case-sensitive matching for CHO, CHO-K1, CHO-S.
      - Negative keywords subtract penalties.
    Candidate must achieve score >= min_score AND match at least ONE anchor keyword.
    Returns (is_relevant, score, match_percentage, positive_matches, negative_matches).
    """
    full_text = f"{title} {abstract_text}"

    # 1. Title keyword matching
    title_anchors: list[str] = []
    title_context: list[str] = []

    if _CHO_CASE_SENSITIVE_PATTERN.search(title):
        title_anchors.append("cho (case-sensitive)")

    for kw in _BIOPROCESS_ANCHOR_KEYWORDS:
        pat = _POSITIVE_BIOPROCESS_PATTERNS.get(kw) or _build_keyword_regex(kw)
        if kw == "protein a":
            if _PROTEIN_A_PATTERN.search(title) and _PROTEIN_A_COOCCUR_PATTERN.search(full_text):
                title_anchors.append("protein a")
        elif kw in _VACCINE_MODALITY_KEYWORDS:
            if pat.search(title):
                if _VACCINE_PROCESS_COOCCUR_PATTERN.search(full_text):
                    title_anchors.append(kw)
                else:
                    title_context.append(f"{kw} (unpaired)")
        elif pat.search(title):
            title_anchors.append(kw)

    for kw in _BIOPROCESS_CONTEXT_KEYWORDS:
        pat = _POSITIVE_BIOPROCESS_PATTERNS.get(kw) or _build_keyword_regex(kw)
        if pat.search(title):
            title_context.append(kw)

    # 2. Abstract keyword matching (items not already matched in title)
    abstract_anchors: list[str] = []
    abstract_context: list[str] = []
    if abstract_text:
        if _CHO_CASE_SENSITIVE_PATTERN.search(abstract_text) and "cho (case-sensitive)" not in title_anchors:
            abstract_anchors.append("cho (case-sensitive)")

        for kw in _BIOPROCESS_ANCHOR_KEYWORDS:
            if kw in title_anchors:
                continue
            pat = _POSITIVE_BIOPROCESS_PATTERNS.get(kw) or _build_keyword_regex(kw)
            if kw == "protein a":
                if _PROTEIN_A_PATTERN.search(abstract_text) and _PROTEIN_A_COOCCUR_PATTERN.search(full_text):
                    abstract_anchors.append("protein a")
            elif kw in _VACCINE_MODALITY_KEYWORDS:
                if pat.search(abstract_text):
                    if _VACCINE_PROCESS_COOCCUR_PATTERN.search(full_text):
                        abstract_anchors.append(kw)
                    elif f"{kw} (unpaired)" not in title_context:
                        abstract_context.append(f"{kw} (unpaired)")
            elif pat.search(abstract_text):
                abstract_anchors.append(kw)

        for kw in _BIOPROCESS_CONTEXT_KEYWORDS:
            if kw in title_context:
                continue
            pat = _POSITIVE_BIOPROCESS_PATTERNS.get(kw) or _build_keyword_regex(kw)
            if pat.search(abstract_text):
                abstract_context.append(kw)

    all_anchors = list(dict.fromkeys(title_anchors + abstract_anchors))
    all_context = list(dict.fromkeys(title_context + abstract_context))

    # Pairing rule for bioprocess & biomanufacturing:
    # Raise "bioprocess" and "biomanufacturing" to weight 2 ONLY when paired with a second anchor.
    other_anchors = [a for a in all_anchors if a not in ("bioprocess", "biomanufacturing")]
    is_paired = len(other_anchors) >= 1

    # 3. Title Score (x2 multiplier)
    title_score = 0
    for a in title_anchors:
        if a == "cho (case-sensitive)":
            w = 2
        elif a in ("bioprocess", "biomanufacturing"):
            w = 2 if is_paired else 1
        else:
            w = _BIOPROCESS_ANCHOR_KEYWORDS.get(a, 2)
        title_score += w * 2

    for c in title_context:
        w = _BIOPROCESS_CONTEXT_KEYWORDS.get(c, 1)
        title_score += w * 2

    # 4. Abstract Score (x1 multiplier, capped at _ABSTRACT_SCORE_CAP)
    abstract_raw = 0
    for a in abstract_anchors:
        if a == "cho (case-sensitive)":
            w = 2
        elif a in ("bioprocess", "biomanufacturing"):
            w = 2 if is_paired else 1
        else:
            w = _BIOPROCESS_ANCHOR_KEYWORDS.get(a, 2)
        abstract_raw += w

    for c in abstract_context:
        w = _BIOPROCESS_CONTEXT_KEYWORDS.get(c, 1)
        abstract_raw += w

    abstract_score = min(_ABSTRACT_SCORE_CAP, abstract_raw)

    # 5. Negative Penalties
    neg_matches: list[str] = []
    neg_penalty = 0
    for kw, penalty in _NEGATIVE_OFF_TOPIC_KEYWORDS.items():
        pat = _NEGATIVE_OFF_TOPIC_PATTERNS.get(kw) or _build_keyword_regex(kw)
        if pat.search(full_text):
            neg_matches.append(kw)
            neg_penalty += penalty

    total_score = (title_score + abstract_score) - neg_penalty
    is_relevant = (total_score >= min_score) and (len(all_anchors) > 0)
    match_percentage = min(100.0, max(0.0, (total_score / score_ceiling) * 100.0))
    match_percentage = round(match_percentage, 1)

    pos_matches = all_anchors + all_context
    return is_relevant, total_score, match_percentage, pos_matches, neg_matches


def log_filtered_item(
    title: str,
    score: int,
    threshold: int,
    source_id: str,
    pos_matches: list[str],
    neg_matches: list[str],
    query_id: str = "",
) -> None:
    """Record an item filtered by evaluate_bioprocess_relevance to storage/filtered_items_log.jsonl."""
    _FILTERED_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "title": title,
        "relevance_score": score,
        "threshold": threshold,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "query_id": query_id,
        "positive_matches": pos_matches,
        "negative_matches": neg_matches,
    }
    with _FILTERED_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# -- Paraphrase Generation with Retry-With-Backoff ------------------------------

_PARAPHRASE_PROMPT = """You are a scientific bioprocess research assistant summarizing a new paper for an executive literature digest.

Write a fresh, original 2-3 sentence synthesis of the paper's key finding and bioprocess relevance based on the information below.

Paper title: {title}
Authors: {authors} ({publication_date})
Source excerpt:
\"\"\"{source_excerpt}\"\"\"

STRICT RULES:
1. Write 2-3 concise sentences in your own words.
2. Focus on: What was demonstrated, what technology/method was used, and why it matters for bioprocessing or protein production.
3. NEVER copy verbatim phrases longer than 4-5 words from the excerpt.
4. Do NOT use introductory filler like "This paper presents" or "The authors demonstrate". Start directly with the technical subject or core insight.
"""


def generate_paraphrase(
    item: dict[str, Any],
    query_id: str = "",
    dry_run: bool = False,
) -> tuple[str, str]:
    """
    Generate a 2-3 sentence synthesis using Gemini API with retry-backoff
    specifically checking exception status code attributes (429/503).
    When dry_run is active, checks and updates storage/dry_run_llm_cache.json.
    Returns (paraphrase_text, synthesis_method) where synthesis_method is
    'gemini' or 'fallback_template'.
    """
    item_hash = _compute_item_hash(item, query_id)

    if dry_run:
        cached = get_cached_paraphrase(item_hash)
        if cached:
            cached_text, cached_method = cached
            log.info("[DRY RUN] Cache hit for %s -- skipping LLM call", item_hash[:16])
            return cached_text, cached_method

    title = item.get("title") or "Unknown"
    authors = ", ".join(item.get("authors") or []) or "Unknown"
    pub_date = str(item.get("publication_date") or "")
    transient_abstract = item.get("_transient_abstract") or item.get("source_text") or ""
    source_basis = item.get("source_basis") or ("title_and_abstract" if transient_abstract.strip() else "title_only")

    # If only a title is available, do NOT call the LLM (use the fallback template, since a title-only summary invites invented details)
    if source_basis == "title_only" or not transient_abstract.strip():
        log.info("  [SOURCE_TITLE_ONLY] Only title available for '%s'; using fallback template to prevent invented details.", title)
        fallback = (
            f"Investigation into {title.lower().rstrip('.')}, evaluating operational "
            f"parameters and process performance characteristics. The results demonstrate "
            f"methodological strategies relevant to bioprocess optimization."
        )
        if dry_run:
            cache_paraphrase(item_hash, query_id, title, fallback, synthesis_method="fallback_template")
        return fallback, "fallback_template"

    source_text = transient_abstract or item.get("source_text") or title

    global _daily_quota_exhausted
    client = _get_llm_client() if not _daily_quota_exhausted else None

    if client and not _daily_quota_exhausted:
        prompt = _PARAPHRASE_PROMPT.format(
            title=title,
            authors=authors,
            publication_date=pub_date,
            source_excerpt=source_text[:1500],
        )

        for attempt in range(_MAX_LLM_RETRIES + 1):
            try:
                record_call("literature_scout")
                response = client.models.generate_content(
                    model=_llm_model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=300,
                    ),
                )
                text = (response.text or "").strip()
                if text:
                    # Enforce 7-word overlap guard against the transient abstract
                    if check_7word_overlap(text, transient_abstract):
                        log.warning(
                            "  [OVERLAP_GUARD] Generated paraphrase contains 7+ word verbatim overlap with abstract. "
                            "Falling back to template for '%s'.",
                            title,
                        )
                        break

                    if dry_run:
                        cache_paraphrase(item_hash, query_id, title, text, synthesis_method="gemini")
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
                    time.sleep(delay)
                else:
                    log.error(
                        "  [LLM_API_ERROR] Gemini API failed (status_code=%s, attempt %d/%d): %s",
                        status_code, attempt + 1, _MAX_LLM_RETRIES, exc,
                    )
                    break

    # Fallback paraphrase template
    fallback = (
        f"Investigation into {title.lower().rstrip('.')}, evaluating operational "
        f"parameters and process performance characteristics. The results demonstrate "
        f"methodological strategies relevant to bioprocess optimization."
    )
    if dry_run:
        cache_paraphrase(item_hash, query_id, title, fallback, synthesis_method="fallback_template")
    return fallback, "fallback_template"


# -- Output Helpers (Matches regulatory_watch.py schema exactly) ----------------


def _build_record(
    item: dict[str, Any],
    description: str,
    query_id: str,
    index_url: str,
    synthesis_method: str = "gemini",
    source_basis: str = "title_and_abstract",
    match_percentage: float = 0.0,
    recency_bonus: float = 0.0,
    pub_year_used: Optional[int] = None,
    stale: Optional[bool] = None,
    year_unknown: bool = False,
) -> dict[str, Any]:
    """
    Assemble a pending_items.jsonl record matching regulatory_watch.py schema exactly.
    Includes synthesis_method ('gemini' vs 'fallback_template'), source_basis ('title_and_abstract' vs 'title_only'),
    and ranking metadata. Abstract text is never persisted to disk.
    """
    url = item.get("url")
    url_unknown = not bool(url)

    pub_date = item.get("publication_date")
    date_unknown = not bool(pub_date)

    agency = item.get("agency") or ("PubMed" if item.get("source") == "pubmed" else ("bioRxiv" if item.get("source") == "biorxiv" else "Literature"))

    # Compute content hash of title + description
    raw_content = f"{item.get('title', '')}::{description}"
    content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    return {
        "id":               str(uuid.uuid4()),
        "source_type":      "literature",
        "title":            (item.get("title") or "").strip() or "Untitled paper",
        "agency":           agency,
        "url":              url,
        "url_unknown":      url_unknown,
        "publication_date": pub_date,
        "date_unknown":     date_unknown,
        "description":      description.strip(),
        "synthesis_method": synthesis_method,
        "source_basis":     source_basis,
        "detected_at":      datetime.now(timezone.utc).isoformat(),
        "content_hash":     content_hash,
        "source_id":        query_id,
        "index_url":        index_url,
        "match_percentage": match_percentage,
        "recency_bonus":    recency_bonus,
        "pub_year_used":    pub_year_used,
        "stale":            stale,
        "year_unknown":     year_unknown,
        "model_name":       _llm_model if synthesis_method == "gemini" else None,
        "retrieval_method": "rest",
        "config_versions":  {"taxonomy_version": "1.1", "queries_version": "1.1"},
    }


def _append_record(record: dict[str, Any], dry_run: bool) -> None:
    line = json.dumps(record, ensure_ascii=False)
    if dry_run:
        log.info("[DRY RUN] Would append -> %s", line)
        return
    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _OUTPUT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    log.info("  [OK] Appended: %s", record.get("title"))


def _normalize_title_for_dedupe(title: str) -> str:
    """Normalize a title for cross-query deduplication: lowercase, strip punctuation and collapse whitespace."""
    if not title:
        return ""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(cleaned.split())


# -- Main Run Logic ------------------------------------------------------------


_MAX_RUN_LLM_CALLS = 12
_GUARANTEED_QUERIES = (
    "expression_construct_troubleshooting",
    "early_phase_cgmp_manufacturing",
    "microbiome_commensal_platform",
)


def allocate_llm_slots(
    candidates_by_query: dict[str, list[dict[str, Any]]],
    query_order: list[str],
    max_calls: int = _MAX_RUN_LLM_CALLS,
    guaranteed_queries: tuple[str, ...] = _GUARANTEED_QUERIES,
) -> set[tuple[str, int]]:
    """
    Allocate up to `max_calls` LLM slots across queries:
    1. Guarantee at least 1 LLM call for each of the queries in `guaranteed_queries`
       if they have any passing items with abstracts (allocated to its #1 best-scoring eligible item).
    2. Allocate remaining slots round-robin across all queries in `query_order`
       (best-scoring eligible item from each query first, then second-best, etc.).
    Note: Items with source_basis == "title_only" or empty abstracts are ineligible for LLM calls.
    Returns a set of (q_id, item_index) tuples allocated to LLM synthesis.
    """
    allocated: set[tuple[str, int]] = set()
    calls_used = 0

    def is_eligible(rec: dict[str, Any]) -> bool:
        if rec.get("source_basis") == "title_only":
            return False
        if "_transient_abstract" in rec and not rec.get("_transient_abstract", "").strip():
            return False
        return True

    # 1. Guarantee Phase: 1 LLM call for each guaranteed query with eligible passing items
    for q_id in guaranteed_queries:
        if q_id in candidates_by_query:
            recs = candidates_by_query[q_id]
            for idx, rec in enumerate(recs):
                if is_eligible(rec):
                    if calls_used < max_calls:
                        allocated.add((q_id, idx))
                        calls_used += 1
                    break

    # 2. Round-Robin Phase across all queries in configured order
    max_items = max((len(recs) for recs in candidates_by_query.values()), default=0)
    for round_idx in range(max_items):
        for q_id in query_order:
            if q_id not in candidates_by_query:
                continue
            recs = candidates_by_query[q_id]
            if round_idx < len(recs):
                rec = recs[round_idx]
                if not is_eligible(rec):
                    continue
                pair = (q_id, round_idx)
                if pair not in allocated:
                    if calls_used < max_calls:
                        allocated.add(pair)
                        calls_used += 1
                    else:
                        return allocated

    return allocated


def run(
    queries_path: Path = _DEFAULT_QUERIES,
    state_path:   Path = _DEFAULT_STATE,
    limit:        Optional[int] = None,
    dry_run:      bool = False,
    filter_only:  bool = False,
) -> int:
    """Run literature scout search across configured queries."""
    log.info("Starting Literature Scout run...")
    log.info("  [BIORXIV_NOT_ACTIVE] bioRxiv monitoring is currently inactive; PubMed (NCBI E-utilities) is the sole active source.")
    state = load_state(state_path)
    seen_ids: dict[str, str] = state.get("seen_ids", {})

    # Check MCP servers configured in mcp_config.json
    log.info("Checking MCP server connections (PubMed)...")
    mcp_pubmed_ok, p_status = check_mcp_server_connection("pubmed")
    if not mcp_pubmed_ok:
        log.info("  -> Falling back to direct NCBI E-utilities REST API.")

    # Determine candidate fetch limit and sort order
    if limit is None:
        fetch_limit = 30 if filter_only else 15
    else:
        fetch_limit = limit

    sort_order = "relevance" if filter_only else "pub_date"

    # Load queries, global relevance threshold, and publication window
    queries = []
    default_min_score = 2
    pub_window_years = 3
    if queries_path.exists():
        try:
            data = json.loads(queries_path.read_text(encoding="utf-8"))
            default_min_score = data.get("min_relevance_score", 2)
            pub_window_years = data.get("publication_window_years", 3)
            queries = [q for q in data.get("queries", []) if q.get("enabled", True)]
        except Exception as exc:
            log.warning("Could not read %s: %s", queries_path, exc)

    if not queries:
        queries = [{
            "id": "bioprocess_default",
            "name": "Bioprocess & Protein Production",
            "pubmed_query": "(CHO cells OR bioreactor) AND (perfusion OR chromatography) AND (monoclonal antibody OR recombinant)",
            "enabled": True,
        }]

    new_items_count = 0
    llm_calls_this_run = 0
    query_statuses: dict[str, dict[str, Any]] = {}
    query_stats: dict[str, dict[str, Any]] = {}
    candidates_by_query: dict[str, dict[str, Any]] = {}
    query_names: dict[str, str] = {}

    for q in queries:
        q_id   = q.get("id", "query")
        q_name = q.get("name", q_id)
        query_names[q_id] = q_name
        pubmed_q = q.get("pubmed_query")
        min_score = q.get("min_relevance_score", default_min_score)

        query_stats[q_id] = {
            "total": 0,
            "passed": 0,
            "filtered": 0,
            "anchor_counter": collections.Counter(),
        }

        log.info("Checking query '%s'...", q_name)

        if not pubmed_q:
            query_statuses[q_id] = {"name": q_name, "status": "NO_NEW_ITEMS", "detail": "No PubMed query defined"}
            continue

        query_index_url = f"{_NCBI_ESEARCH_URL}?term={urllib.parse.quote(pubmed_q)}"
        try:
            pmids = search_pubmed(pubmed_q, limit=fetch_limit, sort=sort_order, pub_window_years=pub_window_years)
            new_pmids = [p for p in pmids if p not in seen_ids] if not filter_only else pmids
            if not new_pmids:
                query_statuses[q_id] = {"name": q_name, "status": "NO_NEW_ITEMS", "detail": f"0 new PMIDs (found {len(pmids)})"}
                log.info("  [NO_NEW_ITEMS] Query '%s' on PubMed completed successfully: 0 new items found.", q_name)
                continue

            records = fetch_pubmed_summaries(new_pmids)
            abstracts_map = fetch_pubmed_abstracts(new_pmids)
            query_stats[q_id]["total"] = len(records)

            if filter_only:
                for rec in records:
                    pmid = rec["pmid"]
                    title = rec.get("title", "")
                    abs_text = abstracts_map.get(pmid, "")
                    rec["_transient_abstract"] = abs_text
                    rec["source_basis"] = "title_and_abstract" if abs_text.strip() else "title_only"
                    is_rel, score, match_pct, pos_m, neg_m = evaluate_bioprocess_relevance(
                        title, abs_text, min_score=min_score
                    )
                    if is_rel:
                        query_stats[q_id]["passed"] += 1
                        matched_anchors = [k for k in pos_m if k in _BIOPROCESS_ANCHOR_KEYWORDS or k == "cho (case-sensitive)"]
                        query_stats[q_id]["anchor_counter"].update(matched_anchors)
                    else:
                        query_stats[q_id]["filtered"] += 1

                    preview_entry = {
                        "source": rec.get("source", "pubmed"),
                        "source_id": pmid,
                        "query_id": q_id,
                        "query_name": q_name,
                        "title": title,
                        "score": score,
                        "threshold": min_score,
                        "passed": is_rel,
                        "source_basis": rec["source_basis"],
                        "match_percentage": match_pct,
                        "anchor_matches": [k for k in pos_m if k in _BIOPROCESS_ANCHOR_KEYWORDS or k == "cho (case-sensitive)"],
                        "context_matches": [k for k in pos_m if k in _BIOPROCESS_CONTEXT_KEYWORDS],
                        "negative_matches": neg_m,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    _FILTER_PREVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with _FILTER_PREVIEW_FILE.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(preview_entry, ensure_ascii=False) + "\n")
                    log.info(
                        "  [FILTER_PREVIEW] Query '%s': '%s' -> %s (score=%d, threshold=%d, anchor=%s, context=%s, neg=%s, basis=%s)",
                        q_name, title, "PASS" if is_rel else "FILTERED", score, min_score,
                        preview_entry["anchor_matches"], preview_entry["context_matches"], neg_m, rec["source_basis"],
                    )
                query_statuses[q_id] = {"name": q_name, "status": "OK", "detail": f"{len(records)} candidates previewed"}
                continue

            valid_records = []
            for rec in records:
                pmid = rec["pmid"]
                title = rec.get("title", "")
                abs_text = abstracts_map.get(pmid, "")
                rec["_transient_abstract"] = abs_text
                rec["source_basis"] = "title_and_abstract" if abs_text.strip() else "title_only"

                is_rel, score, match_pct, pos_m, neg_m = evaluate_bioprocess_relevance(
                    title, abs_text, min_score=min_score
                )
                recency_bonus, pub_year = calculate_recency_bonus(rec.get("publication_date"))
                stale = (pub_year < 2023) if pub_year is not None else None
                year_unknown = (pub_year is None)

                rec["_ranking_meta"] = {
                    "score": score,
                    "match_percentage": match_pct,
                    "recency_bonus": recency_bonus,
                    "pub_year_used": pub_year,
                    "stale": stale,
                    "year_unknown": year_unknown,
                }

                if not is_rel:
                    query_stats[q_id]["filtered"] += 1
                    log.info(
                        "  [FILTERED_OFF_TOPIC] Query '%s': '%s' (score=%d, match=%.1f%% < threshold=%d; pos=%s, neg=%s)",
                        q_name, title, score, match_pct, min_score, pos_m, neg_m,
                    )
                    log_filtered_item(
                        title=title,
                        score=score,
                        threshold=min_score,
                        source_id=pmid,
                        pos_matches=pos_m,
                        neg_matches=neg_m,
                        query_id=q_id,
                    )
                    seen_ids[pmid] = datetime.now(timezone.utc).isoformat()
                else:
                    query_stats[q_id]["passed"] += 1
                    matched_anchors = [k for k in pos_m if k in _BIOPROCESS_ANCHOR_KEYWORDS or k == "cho (case-sensitive)"]
                    query_stats[q_id]["anchor_counter"].update(matched_anchors)
                    valid_records.append(rec)

            if not valid_records:
                query_statuses[q_id] = {"name": q_name, "status": "FILTERED_ALL", "detail": f"{len(new_pmids)} items all off-topic"}
                log.info("  [NO_NEW_ITEMS] Query '%s' on PubMed: %d new item(s) found, all filtered as off-topic.", q_name, len(new_pmids))
                continue

            # Rank valid records by relevance score (composite match_percentage + recency_bonus)
            valid_records.sort(
                key=lambda r: -(float(r["_ranking_meta"]["match_percentage"]) + float(r["_ranking_meta"]["recency_bonus"]))
            )

            # Keep top 3 passing items per query
            top_records = valid_records[:3]
            candidates_by_query[q_id] = {
                "name": q_name,
                "index_url": query_index_url,
                "records": top_records,
            }

        except NetworkFetchError as exc:
            if exc.is_rate_limited:
                log.error("  [RATE_LIMITED] Query '%s' failed due to rate limiting (HTTP %s): %s", q_name, exc.status_code, exc)
            else:
                log.error("  [FETCH_ERROR] Query '%s' failed (HTTP %s): %s", q_name, exc.status_code, exc)
            query_statuses[q_id] = {"name": q_name, "status": "FAILED", "detail": str(exc)}
            # NOTE: On failure, do NOT add PMIDs to seen_ids!
            continue

    # Allocate LLM synthesis slots and synthesize items
    per_query_counts: dict[str, dict[str, int]] = {q.get("id", "query"): {"llm": 0, "fallback": 0} for q in queries}
    total_llm_used = 0
    total_fallback_used = 0

    if not filter_only and candidates_by_query:
        query_order = [q.get("id", "query") for q in queries]
        passing_records_map = {q_id: c["records"] for q_id, c in candidates_by_query.items()}
        llm_assigned = allocate_llm_slots(
            candidates_by_query=passing_records_map,
            query_order=query_order,
            max_calls=_MAX_RUN_LLM_CALLS,
            guaranteed_queries=_GUARANTEED_QUERIES,
        )

        # Pre-flight gate check for planned LLM calls
        global _preflight_checked
        if not _preflight_checked and len(llm_assigned) > 0:
            if not check_preflight_gate(len(llm_assigned), "literature_scout"):
                log.info("[QUOTA_GUARD] Pre-flight gate aborted by reviewer -- 0 API calls made.")
                return 0
            _preflight_checked = True

        # Cross-query deduplication registries across all queries in this run
        deduped_records: dict[str, dict[str, Any]] = {}
        pmid_to_key: dict[str, str] = {}
        title_to_key: dict[str, str] = {}

        for q in queries:
            q_id = q.get("id", "query")
            if q_id not in candidates_by_query:
                continue
            c_data = candidates_by_query[q_id]
            recs = c_data["records"]
            query_index_url = c_data["index_url"]

            for idx, rec in enumerate(recs):
                pmid = str(rec.get("pmid", "")).strip()
                title = rec.get("title", "")
                norm_title = _normalize_title_for_dedupe(title)
                basis = rec.get("source_basis", "title_and_abstract")

                # Check if this item is a duplicate of an item already synthesized in this run
                matched_key = None
                if pmid and pmid in pmid_to_key:
                    matched_key = pmid_to_key[pmid]
                elif norm_title and norm_title in title_to_key:
                    matched_key = title_to_key[norm_title]

                if matched_key and deduped_records[matched_key]["record"].get("synthesis_method") in ("gemini", "dry_run_cache"):
                    # Existing record already has LLM synthesis -- reuse it and do not burn an extra API call!
                    existing_llm_rec = deduped_records[matched_key]["record"]
                    desc = existing_llm_rec.get("description", "")
                    method = existing_llm_rec.get("synthesis_method", "gemini")
                    log.info(
                        "  [DEDUPE] Candidate '%s' (PMID %s) already synthesized via LLM; reusing description.",
                        title, pmid or "N/A",
                    )
                elif (q_id, idx) in llm_assigned and basis != "title_only" and llm_calls_this_run < _MAX_RUN_LLM_CALLS:
                    desc, method = generate_paraphrase(rec, query_id=q_id, dry_run=dry_run)
                    if method in ("gemini", "dry_run_cache"):
                        if method == "gemini":
                            llm_calls_this_run += 1
                        per_query_counts[q_id]["llm"] += 1
                        total_llm_used += 1
                    else:
                        per_query_counts[q_id]["fallback"] += 1
                        total_fallback_used += 1
                else:
                    if basis == "title_only":
                        log.info("  [SOURCE_TITLE_ONLY] Title-only record '%s'; using fallback template.", title)
                    else:
                        log.warning(
                            "  [LLM_CAP_REACHED] Per-run LLM cap (%d calls) reached. Using fallback template for '%s'.",
                            _MAX_RUN_LLM_CALLS, title,
                        )
                    desc = (
                        f"Investigation into {title.lower().rstrip('.')}, evaluating operational "
                        f"parameters and process performance characteristics. The results demonstrate "
                        f"methodological strategies relevant to bioprocess optimization."
                    )
                    method = "fallback_template"
                    per_query_counts[q_id]["fallback"] += 1
                    total_fallback_used += 1

                meta = rec.get("_ranking_meta", {})
                out_rec = _build_record(
                    rec,
                    desc,
                    query_id=q_id,
                    index_url=query_index_url,
                    synthesis_method=method,
                    source_basis=basis,
                    match_percentage=meta.get("match_percentage", 0.0),
                    recency_bonus=meta.get("recency_bonus", 0.0),
                    pub_year_used=meta.get("pub_year_used"),
                    stale=meta.get("stale"),
                    year_unknown=meta.get("year_unknown", False),
                )

                if matched_key is None:
                    canonical_key = f"pmid_{pmid}" if pmid else f"title_{norm_title}"
                    deduped_records[canonical_key] = {"record": out_rec, "pmid": pmid, "norm_title": norm_title}
                    if pmid:
                        pmid_to_key[pmid] = canonical_key
                    if norm_title:
                        title_to_key[norm_title] = canonical_key
                else:
                    existing = deduped_records[matched_key]["record"]
                    existing_method = existing.get("synthesis_method", "")
                    existing_is_llm = existing_method in ("gemini", "dry_run_cache")
                    new_is_llm = method in ("gemini", "dry_run_cache")

                    if new_is_llm and not existing_is_llm:
                        deduped_records[matched_key] = {"record": out_rec, "pmid": pmid, "norm_title": norm_title}
                        log.info(
                            "  [DEDUPE] Replaced fallback-template record with LLM-synthesized record for '%s' (PMID %s).",
                            title, pmid or "N/A",
                        )
                    elif existing_is_llm and not new_is_llm:
                        log.info(
                            "  [DEDUPE] Discarded fallback duplicate in favor of existing LLM synthesis for '%s' (PMID %s).",
                            title, pmid or "N/A",
                        )
                    else:
                        existing_score = float(existing.get("match_percentage", 0.0)) + float(existing.get("recency_bonus", 0.0))
                        new_score = float(out_rec.get("match_percentage", 0.0)) + float(out_rec.get("recency_bonus", 0.0))
                        if new_score > existing_score:
                            deduped_records[matched_key] = {"record": out_rec, "pmid": pmid, "norm_title": norm_title}
                            log.info(
                                "  [DEDUPE] Retained higher-scoring candidate (%.1f > %.1f) for duplicate '%s' (PMID %s).",
                                new_score, existing_score, title, pmid or "N/A",
                            )
                        else:
                            log.info(
                                "  [DEDUPE] Discarded duplicate candidate for '%s' (PMID %s); retained existing record with equal/higher score.",
                                title, pmid or "N/A",
                            )

            q_llm = per_query_counts[q_id]["llm"]
            q_fb = per_query_counts[q_id]["fallback"]
            query_statuses[q_id] = {
                "name": c_data["name"],
                "status": "OK",
                "detail": f"{len(recs)} item(s) processed ({q_llm} LLM, {q_fb} fallback)",
            }

        # Write deduplicated records to pending_items.jsonl
        for entry in deduped_records.values():
            out_rec = entry["record"]
            pmid = entry["pmid"]
            _append_record(out_rec, dry_run=dry_run)
            src_id = pmid or out_rec.get("source_id")
            if src_id:
                seen_ids[src_id] = datetime.now(timezone.utc).isoformat()
            new_items_count += 1

    if not dry_run and not filter_only:
        state["seen_ids"] = seen_ids
        save_state(state_path, state)

    # Print per-query status summary with candidate counts and top anchor terms
    print()
    print("=" * 84)
    print("  Literature Scout Query Summary:")
    ok_count = sum(1 for s in query_statuses.values() if s["status"] in ("OK", "NO_NEW_ITEMS", "FILTERED_ALL"))
    failed_count = sum(1 for s in query_statuses.values() if s["status"] == "FAILED")
    for q_id, info in query_statuses.items():
        st = query_stats.get(q_id, {"passed": 0, "filtered": 0, "total": 0, "anchor_counter": collections.Counter()})
        top_anchors = st["anchor_counter"].most_common(3)
        top_str = ", ".join(f"{term} ({cnt})" for term, cnt in top_anchors) if top_anchors else "none"
        print(f"    * {info['name']:<42} [{info['status']:<12}] ({st['passed']} pass / {st['filtered']} filtered / {st['total']} total | Top anchors: {top_str})")
    if not filter_only:
        print("-" * 84)
        print(f"  Synthesis Allocation: LLM calls used {total_llm_used}/{_MAX_RUN_LLM_CALLS}, fallback-template items {total_fallback_used}")
        if per_query_counts:
            print("  Per-Query Breakdown:")
            for q_id, counts in per_query_counts.items():
                q_name = query_names.get(q_id, q_id)
                print(f"    * {q_name:<42} : {counts['llm']} LLM, {counts['fallback']} fallback")
    print("=" * 84)

    log.info(
        "Literature Scout completed. %d new item(s) found. (%d queries OK, %d FAILED)",
        new_items_count, ok_count, failed_count,
    )

    if failed_count > 0:
        log.warning("[PARTIAL] %d query/queries failed out of %d total.", failed_count, len(query_statuses))
        return 2

    return 0


# -- CLI ------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="literature_scout",
        description="BioLitAgent Literature Scout -- monitors PubMed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--queries", default=str(_DEFAULT_QUERIES), metavar="PATH")
    parser.add_argument("--state",   default=str(_DEFAULT_STATE),   metavar="PATH")
    parser.add_argument("--limit",   type=int, default=None, help="Max candidates fetched per query (default: 15 live, 30 --filter-only).")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files.")
    parser.add_argument("--filter-only", action="store_true", help="Run queries and log candidate relevance to storage/filter_preview.jsonl without LLM calls or pending writes.")
    parser.add_argument("--model",   default=_DEFAULT_MODEL, help="Gemini model.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    global _llm_model
    _llm_model = args.model
    return run(
        queries_path=Path(args.queries),
        state_path=Path(args.state),
        limit=args.limit,
        dry_run=args.dry_run,
        filter_only=args.filter_only,
    )


if __name__ == "__main__":
    sys.exit(main())
