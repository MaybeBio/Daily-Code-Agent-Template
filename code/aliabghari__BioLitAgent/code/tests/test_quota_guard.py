"""
tests/test_quota_guard.py
-------------------------
Unit tests verifying the Quota Guard system: call counting, pre-flight gate,
error parsing, agent degradation, orchestration lock, and retry-with-backoff.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import biolitagent.agents.literature_scout
import biolitagent.config.quota_guard
from biolitagent.config.quota_guard import (
    DEFAULT_DAILY_LIMIT,
    SAFETY_MARGIN,
    check_preflight_gate,
    get_usage_today,
    is_daily_exhaustion,
    parse_quota_failure,
    record_call,
    save_usage,
)
from biolitagent.agents.regulatory_watch import ExtractionStatus, _STATUS_META
from biolitagent.agents.literature_scout import (
    generate_paraphrase,
    _build_record as build_lit_record,
)
from biolitagent.agents.run_all import _format_agent_status, AgentRunResult


class TestQuotaGuardCore(unittest.TestCase):
    def setUp(self):
        # Use a temporary file for quota_usage.json during testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_usage_file = Path(self.temp_dir.name) / "quota_usage.json"
        self.orig_usage_file = biolitagent.config.quota_guard._USAGE_FILE
        biolitagent.config.quota_guard._USAGE_FILE = self.test_usage_file

    def tearDown(self):
        biolitagent.config.quota_guard._USAGE_FILE = self.orig_usage_file
        self.temp_dir.cleanup()

    def test_record_call_and_usage(self):
        usage = get_usage_today()
        self.assertEqual(usage["calls_made"], 0)
        self.assertEqual(usage["calls_by_agent"]["literature_scout"], 0)

        # Record calls from different agents
        record_call("literature_scout")
        record_call("literature_scout")
        record_call("regulatory_watch")

        new_usage = get_usage_today()
        self.assertEqual(new_usage["calls_made"], 3)
        self.assertEqual(new_usage["calls_by_agent"]["literature_scout"], 2)
        self.assertEqual(new_usage["calls_by_agent"]["regulatory_watch"], 1)

    def test_quota_error_parsing(self):
        # 1. Structured Google GenAI 429 error with daily quotaId
        mock_exc_daily = Exception(
            "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': [{'@type': "
            "'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'RATE_LIMIT_EXCEEDED', "
            "'domain': 'googleapis.com', 'metadata': {'quotaId': "
            "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}}]}}"
        )
        is_q, q_id, delay = parse_quota_failure(mock_exc_daily)
        self.assertTrue(is_q)
        self.assertEqual(q_id, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        self.assertTrue(is_daily_exhaustion(q_id, str(mock_exc_daily)))

        # 2. Transient per-minute 429 error
        mock_exc_minute = Exception(
            "429 RESOURCE_EXHAUSTED. {'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}"
        )
        is_q2, q_id2, _ = parse_quota_failure(mock_exc_minute)
        self.assertTrue(is_q2)
        self.assertEqual(q_id2, "GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        self.assertFalse(is_daily_exhaustion(q_id2, str(mock_exc_minute)))

        # 3. Non-quota 500 error
        mock_exc_500 = Exception("500 Internal Server Error")
        is_q3, q_id3, _ = parse_quota_failure(mock_exc_500)
        self.assertFalse(is_q3)
        self.assertIsNone(q_id3)

    def test_preflight_gate_automatic_pass(self):
        # 0 calls made today -> 20 remaining. Safety margin = 2.
        # Estimated 5 calls <= 18 -> should pass automatically
        passed = check_preflight_gate(5, "test_agent")
        self.assertTrue(passed)

    def test_preflight_gate_prompt_abort(self):
        # Set calls made to 17 -> 3 remaining. Safe threshold = 3 - 2 = 1.
        save_usage({
            "date": biolitagent.config.quota_guard._today_utc(),
            "calls_made": 17,
            "calls_by_agent": {},
        })
        # Estimated 2 calls > safe threshold (1) -> requires prompt
        with patch("builtins.input", return_value="ABORT"):
            passed = check_preflight_gate(2, "test_agent")
            self.assertFalse(passed)

    def test_preflight_gate_prompt_continue(self):
        # Set calls made to 17 -> 3 remaining
        save_usage({
            "date": biolitagent.config.quota_guard._today_utc(),
            "calls_made": 17,
            "calls_by_agent": {},
        })
        # With CONTINUE confirmation -> should proceed
        with patch("builtins.input", return_value="CONTINUE"):
            passed = check_preflight_gate(2, "test_agent")
            self.assertTrue(passed)


class TestAgentDegradation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_usage_file = Path(self.temp_dir.name) / "quota_usage.json"
        self.orig_usage_file = biolitagent.config.quota_guard._USAGE_FILE
        biolitagent.config.quota_guard._USAGE_FILE = self.test_usage_file

    def tearDown(self):
        biolitagent.config.quota_guard._USAGE_FILE = self.orig_usage_file
        self.temp_dir.cleanup()

    def test_regulatory_status_enum(self):
        self.assertIn("SKIPPED_QUOTA_EXHAUSTED", ExtractionStatus.__members__)
        meta = _STATUS_META[ExtractionStatus.SKIPPED_QUOTA_EXHAUSTED]
        self.assertEqual(meta[0], "[!]  SKIPPED_QUOTA_EXHAUSTED")

    def test_literature_scout_graceful_fallback_template(self):
        # Test fallback template generation when Gemini raises daily exhaustion
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED: {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}"
        )

        test_item = {
            "title": "Continuous Chromatography for Monoclonal Antibodies",
            "authors": ["Smith J", "Doe A"],
            "publication_date": "2026-03-01",
            "source_text": "Experimental setup for continuous chromatography.",
        }

        with patch("biolitagent.agents.literature_scout._get_llm_client", return_value=mock_client):
            # Reset daily exhaustion flag for test
            biolitagent.agents.literature_scout._daily_quota_exhausted = False
            desc, method = generate_paraphrase(test_item, query_id="test_query", dry_run=False)

            self.assertEqual(method, "fallback_template")
            self.assertIn("Investigation into continuous chromatography", desc)
            self.assertTrue(biolitagent.agents.literature_scout._daily_quota_exhausted)

            rec = build_lit_record(
                test_item,
                desc,
                query_id="test_query",
                index_url="https://example.com",
                synthesis_method=method,
            )
            self.assertEqual(rec["synthesis_method"], "fallback_template")
            self.assertIsNone(rec["model_name"])

    def test_run_all_status_formatter(self):
        res_quota = AgentRunResult(
            name="regulatory_watch",
            command=["python", "regulatory_watch.py"],
            start_time=0.0,
            exit_code=0,
            stdout="[!]  SKIPPED_QUOTA_EXHAUSTED",
        )
        self.assertEqual(_format_agent_status(res_quota), "[QUOTA_EXHAUSTED: daily limit reached]")

        res_ok = AgentRunResult(
            name="literature_scout",
            command=["python", "literature_scout.py"],
            start_time=0.0,
            exit_code=0,
            stdout="Literature Scout completed.",
        )
        self.assertEqual(_format_agent_status(res_ok), "[OK]")

    def test_orchestration_stdin_lock(self):
        # File lock under BIOLITAGENT_ORCHESTRATED=1
        temp_dir = tempfile.TemporaryDirectory()
        lock_file = Path(temp_dir.name) / ".quota_guard.lock"
        orig_lock = biolitagent.config.quota_guard._LOCK_FILE
        biolitagent.config.quota_guard._LOCK_FILE = lock_file

        try:
            with patch.dict(os.environ, {"BIOLITAGENT_ORCHESTRATED": "1"}):
                # Acquire lock for agent 1
                with biolitagent.config.quota_guard._orchestration_stdin_lock("agent_1"):
                    self.assertTrue(lock_file.exists())
                    # Another process trying atomic open while locked must encounter FileExistsError
                    with self.assertRaises(FileExistsError):
                        os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

                # After exiting context manager, lock should be cleaned up
                self.assertFalse(lock_file.exists())
        finally:
            biolitagent.config.quota_guard._LOCK_FILE = orig_lock
            temp_dir.cleanup()

    def test_pdf_ingestion_retry_and_quota_exhaustion(self):
        import asyncio
        from biolitagent.agents.pdf_ingestion import (
            PdfMetadata,
            generate_paraphrase as generate_pdf_paraphrase,
            _build_record as build_pdf_record,
        )
        import biolitagent.agents.pdf_ingestion as pdf_module

        mock_exc = Exception(
            "429 RESOURCE_EXHAUSTED: {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}"
        )
        setattr(mock_exc, "code", 429)

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = mock_exc

        test_meta = PdfMetadata(
            title="Continuous Perfusion of CHO Cells",
            authors=["Smith, J."],
            doi="10.1000/182",
            publication_year=2026,
            first_page_text="A study on perfusion cell culture.",
            source_checksum="abc456",
        )

        with patch("biolitagent.agents.pdf_ingestion._get_llm_client", return_value=mock_client):
            pdf_module._daily_quota_exhausted = False
            desc, method = asyncio.run(generate_pdf_paraphrase(test_meta, dry_run=False))

            self.assertEqual(method, "fallback_template")
            self.assertIn("Deposited bioprocess research publication", desc)
            self.assertTrue(pdf_module._daily_quota_exhausted)

            rec = build_pdf_record(test_meta, desc, "test.pdf", synthesis_method=method)
            self.assertEqual(rec["synthesis_method"], "fallback_template")
            self.assertIsNone(rec["model_name"])

    def test_pdf_ingestion_transient_retry(self):
        import asyncio
        from unittest.mock import AsyncMock
        from biolitagent.agents.pdf_ingestion import (
            PdfMetadata,
            generate_paraphrase as generate_pdf_paraphrase,
        )
        import biolitagent.agents.pdf_ingestion as pdf_module

        mock_503 = Exception("503 Service Unavailable")
        setattr(mock_503, "code", 503)

        mock_response = MagicMock()
        mock_response.text = "Synthesized original summary of bioprocess results."

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [mock_503, mock_response]

        test_meta = PdfMetadata(
            title="Chromatography Optimization",
            authors=["Doe, A."],
            first_page_text="Chromatographic methods.",
            source_checksum="def789",
        )

        with patch("biolitagent.agents.pdf_ingestion._get_llm_client", return_value=mock_client), \
             patch("biolitagent.agents.pdf_ingestion.asyncio.sleep", new_callable=AsyncMock):
            pdf_module._daily_quota_exhausted = False
            desc, method = asyncio.run(generate_pdf_paraphrase(test_meta, dry_run=False))

            self.assertEqual(method, "gemini")
            self.assertEqual(desc, "Synthesized original summary of bioprocess results.")
            self.assertEqual(mock_client.models.generate_content.call_count, 2)

    def test_pipeline_preflight_gate_orchestration(self):
        from biolitagent.agents.run_all import check_pipeline_preflight_gate

        # 1. Dry run bypasses gate
        self.assertTrue(check_pipeline_preflight_gate(dry_run=True))

        # 2. Tight quota prompts user; abort returns False
        save_usage({
            "date": biolitagent.config.quota_guard._today_utc(),
            "calls_made": 15,
            "calls_by_agent": {},
        })
        os.environ.pop("BIOLITAGENT_PREFLIGHT_CONFIRMED", None)
        with patch("builtins.input", return_value="ABORT"):
            passed = check_pipeline_preflight_gate(dry_run=False)
            self.assertFalse(passed)
            self.assertNotIn("BIOLITAGENT_PREFLIGHT_CONFIRMED", os.environ)

        # 3. Explicit CONTINUE returns True and sets BIOLITAGENT_PREFLIGHT_CONFIRMED=1
        with patch("builtins.input", return_value="CONTINUE"):
            passed = check_pipeline_preflight_gate(dry_run=False)
            self.assertTrue(passed)
            self.assertEqual(os.environ.get("BIOLITAGENT_PREFLIGHT_CONFIRMED"), "1")

        # 4. Child agent skips prompt when BIOLITAGENT_PREFLIGHT_CONFIRMED is 1
        child_passed = check_preflight_gate(10, "literature_scout")
        self.assertTrue(child_passed)
        os.environ.pop("BIOLITAGENT_PREFLIGHT_CONFIRMED", None)


if __name__ == "__main__":
    unittest.main()

