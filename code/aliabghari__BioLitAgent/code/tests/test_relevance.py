"""
tests/test_relevance.py
-----------------------
Unit tests verifying the two-tier bioprocess relevance scoring, regex word-boundary
and plural matching, negative keyword penalty scoping, ranking metadata, and --filter-only mode.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import biolitagent.agents.literature_scout as lit_module
from biolitagent.agents.literature_scout import (
    _BIOPROCESS_ANCHOR_KEYWORDS,
    _BIOPROCESS_CONTEXT_KEYWORDS,
    _POSITIVE_BIOPROCESS_KEYWORDS,
    _build_keyword_regex,
    calculate_recency_bonus,
    evaluate_bioprocess_relevance,
    log_filtered_item,
    run as run_literature_scout,
)
from biolitagent.agents.pdf_ingestion import PdfMetadata, _build_record as build_pdf_record
from biolitagent.agents.review_checkpoint import print_item, print_overview


class TestRelevanceScoring(unittest.TestCase):
    def test_plural_regex_matching(self):
        # 1. Plural regex matching: irregular and regular plurals produce positive matches
        test_cases = [
            ("mAbs", "mab"),
            ("bioreactors", "bioreactor"),
            ("inclusion bodies", "inclusion body"),
            ("monoclonal antibodies", "monoclonal antibody"),
            ("plasmids", "plasmid"),
            ("closed systems", "closed system"),
            ("signal peptides", "signal peptide"),
            ("endotoxins", "endotoxin"),
        ]
        for text, expected_kw in test_cases:
            is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(f"Advances in {text} for biomanufacturing")
            self.assertTrue(is_rel, f"Expected {text} to be relevant, got score={score}")
            self.assertIn(expected_kw, pos, f"Expected {expected_kw} in pos_matches for '{text}'")

        # 2. Word boundaries prevent partial-word collisions on "tea"
        steady_title = "Steady-state perfusion of CHO cells for continuous bioprocessing"
        is_rel_s, score_s, _, pos_s, neg_s = evaluate_bioprocess_relevance(steady_title)
        self.assertTrue(is_rel_s)
        self.assertNotIn("tea", neg_s)

        instead_title = "Instead of batch, integrated continuous manufacturing of mAbs with Protein A capture"
        is_rel_i, score_i, _, pos_i, neg_i = evaluate_bioprocess_relevance(instead_title)
        self.assertTrue(is_rel_i)
        self.assertNotIn("tea", neg_i)

    def test_two_tier_scoring(self):
        # Anchor keywords required: score >= min_score AND at least one anchor match

        # 1. ELISA autoantibodies in lupus (generic context only -> 0 anchors -> filtered)
        lupus_title = "ELISA-based detection of autoantibodies in lupus patients"
        is_rel_l, score_l, match_pct_l, pos_l, neg_l = evaluate_bioprocess_relevance(lupus_title)
        self.assertFalse(is_rel_l)
        self.assertIn("elisa", pos_l)
        self.assertFalse(any(k in _BIOPROCESS_ANCHOR_KEYWORDS for k in pos_l))

        # 2. E. coli UTI title (generic context only -> 0 anchors -> filtered)
        uti_title = "Prevalence and antimicrobial resistance of Escherichia coli in urinary tract infections"
        is_rel_u, score_u, match_pct_u, pos_u, neg_u = evaluate_bioprocess_relevance(uti_title)
        self.assertFalse(is_rel_u)
        self.assertFalse(any(k in _BIOPROCESS_ANCHOR_KEYWORDS for k in pos_u))

        # 3. E. coli inclusion body refolding with signal peptide (anchors + context -> passes)
        valid_title = "E. coli inclusion body refolding and signal peptide optimization for recombinant protein yield"
        is_rel_v, score_v, match_pct_v, pos_v, neg_v = evaluate_bioprocess_relevance(valid_title)
        self.assertTrue(is_rel_v)
        self.assertIn("e. coli", pos_v)
        self.assertIn("inclusion body", pos_v)
        self.assertIn("signal peptide", pos_v)
        self.assertIn("recombinant protein", pos_v)
        self.assertGreaterEqual(score_v, 6)

    def test_negative_keyword_scoping_no_regression(self):
        # Part F regression test: negative penalties applied in full even when "purification" matches
        title = (
            "Acute toxicity and ecotoxicological assessment of heavy metal contamination "
            "in zebrafish embryos following wastewater purification treatment"
        )
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(title)

        self.assertFalse(is_rel, f"Expected is_relevant=False, got {is_rel} with score={score}")
        self.assertEqual(score, -23)
        self.assertIn("purification", pos)
        self.assertIn("zebrafish", neg)
        self.assertIn("heavy metal", neg)
        self.assertIn("wastewater", neg)
        self.assertLess(score, 0)
        self.assertEqual(match_pct, 0.0)

    def test_evaluate_bioprocess_relevance_and_logging(self):
        # Off-topic toxicology
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(
            "LPS-induced oxidative stress and neurotoxicity in zebrafish embryos",
            "Toxicological assessment under heavy metal exposure."
        )
        self.assertFalse(is_rel)
        self.assertIn("zebrafish", neg)
        self.assertLess(score, 0)
        self.assertEqual(match_pct, 0.0)

        # Off-topic tea fermentation
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(
            "Aroma compound dynamics during post-fermentation aging of green tea leaves",
            "Analysis of flavor compounds in fermented tea."
        )
        self.assertFalse(is_rel)
        self.assertIn("tea", neg)
        self.assertLess(score, 2)

        # Relevant bioprocess paper
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(
            "Perfusion culture of CHO cells for continuous monoclonal antibody manufacturing",
            "High viable cell density bioreactor operations and productivity."
        )
        self.assertTrue(is_rel)
        self.assertGreaterEqual(score, 4)
        self.assertIn("cho cells", pos)
        self.assertIn("perfusion", pos)
        self.assertGreaterEqual(match_pct, 40.0)

        # Filtered items log
        temp_dir = tempfile.TemporaryDirectory()
        test_filtered_log = Path(temp_dir.name) / "filtered_items_log.jsonl"
        orig_filtered_log = lit_module._FILTERED_LOG_FILE
        lit_module._FILTERED_LOG_FILE = test_filtered_log

        try:
            log_filtered_item(
                title="LPS toxicology in zebrafish",
                score=-8,
                threshold=2,
                source_id="pmid_12345",
                pos_matches=[],
                neg_matches=["zebrafish", "toxicology"],
                query_id="upstream_perfusion",
            )
            self.assertTrue(test_filtered_log.exists())
            lines = test_filtered_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            logged = json.loads(lines[0])
            self.assertEqual(logged["title"], "LPS toxicology in zebrafish")
            self.assertEqual(logged["relevance_score"], -8)
            self.assertEqual(logged["threshold"], 2)
            self.assertEqual(logged["source_id"], "pmid_12345")
            self.assertEqual(logged["query_id"], "upstream_perfusion")
        finally:
            lit_module._FILTERED_LOG_FILE = orig_filtered_log
            temp_dir.cleanup()

    def test_microbiome_query_and_collision_fix(self):
        # Genuine bioprocess / LBP / commensal vaccine paper
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(
            "Lyophilization and encapsulation of live biotherapeutic bacterial consortia for oral mucosal vaccination",
            "Bioprocess optimization for stabilizing commensal vaccine vectors in the gut microbiota."
        )
        self.assertTrue(is_rel)
        self.assertGreaterEqual(score, 5)
        self.assertIn("live biotherapeutic", pos)
        self.assertIn("encapsulation", pos)
        self.assertIn("lyophilization", pos)
        self.assertEqual(len(neg), 0)

        # Purely observational / clinical FMT cohort study -> filtered
        is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(
            "Fecal microbiota transplantation in patients with recurrent Clostridioides difficile: a prospective dysbiosis cohort",
            "Clinical outcomes and patient symptom resolution following fecal transplant."
        )
        self.assertFalse(is_rel)
        self.assertTrue(any("fecal" in n for n in neg))

    def test_part_e_ranking_and_stale_logic(self):
        # 1. Recency bonus calculations
        bonus_2022, yr_2022 = calculate_recency_bonus(2022)
        self.assertEqual(bonus_2022, 0.0)
        self.assertEqual(yr_2022, 2022)

        bonus_2021, yr_2021 = calculate_recency_bonus("2021")
        self.assertEqual(bonus_2021, 0.0)
        self.assertEqual(yr_2021, 2021)

        bonus_2023, yr_2023 = calculate_recency_bonus("2023-05-01")
        self.assertEqual(bonus_2023, 0.5)
        self.assertEqual(yr_2023, 2023)

        bonus_2024, yr_2024 = calculate_recency_bonus(2024)
        self.assertEqual(bonus_2024, 1.0)
        self.assertEqual(yr_2024, 2024)

        bonus_2025, _ = calculate_recency_bonus(2025)
        self.assertEqual(bonus_2025, 1.5)

        bonus_2026, _ = calculate_recency_bonus(2026)
        self.assertEqual(bonus_2026, 2.0)

        bonus_2035, _ = calculate_recency_bonus(2035)
        self.assertEqual(bonus_2035, 3.0)

        bonus_none, yr_none = calculate_recency_bonus(None)
        self.assertEqual(bonus_none, 0.0)
        self.assertIsNone(yr_none)

        # 2. PDF Ingestion stale logic
        meta_recent = PdfMetadata(
            title="Bioreactor Modeling",
            authors=["A. Scientist"],
            publication_year=2024,
            first_page_text="Perfusion bioreactor for CHO cells",
            source_checksum="cs1",
        )
        rec_recent = build_pdf_record(meta_recent, "Summary of paper", "test.pdf")
        self.assertFalse(rec_recent["stale"])
        self.assertFalse(rec_recent["year_unknown"])
        self.assertEqual(rec_recent["publication_year"], 2024)
        self.assertEqual(rec_recent["recency_bonus"], 1.0)

        meta_stale = PdfMetadata(
            title="Old Bioreactor Paper",
            authors=["B. Scientist"],
            publication_year=2018,
            first_page_text="Early cell culture methods",
            source_checksum="cs2",
        )
        rec_stale = build_pdf_record(meta_stale, "Summary of old paper", "old.pdf")
        self.assertTrue(rec_stale["stale"])
        self.assertFalse(rec_stale["year_unknown"])
        self.assertEqual(rec_stale["recency_bonus"], 0.0)

    def test_new_positive_keywords_weight(self):
        new_kws = [
            "escherichia coli", "e. coli", "inclusion body", "signal peptide",
            "codon optimization", "plasmid", "endotoxin", "sds-page",
            "elisa", "flow cytometry", "cgmp", "first-in-human",
            "phase 1", "closed system", "scale-out", "bacteroides",
            "gut microbiota", "anaerobic", "formulation", "release testing"
        ]
        for kw in new_kws:
            self.assertIn(kw, _POSITIVE_BIOPROCESS_KEYWORDS, f"Missing positive keyword: {kw}")

    def test_filter_only_mode(self):
        # Test --filter-only flag: logs to storage/filter_preview.jsonl without Gemini calls or pending_items writes
        temp_dir = tempfile.TemporaryDirectory()
        test_preview_file = Path(temp_dir.name) / "filter_preview.jsonl"
        test_pending_file = Path(temp_dir.name) / "pending_items.jsonl"
        test_state_file = Path(temp_dir.name) / "literature_state.json"
        test_queries_file = Path(temp_dir.name) / "queries.json"

        orig_preview = lit_module._FILTER_PREVIEW_FILE
        orig_output = lit_module._OUTPUT_FILE
        lit_module._FILTER_PREVIEW_FILE = test_preview_file
        lit_module._OUTPUT_FILE = test_pending_file

        queries_content = {
            "version": "1.1",
            "min_relevance_score": 2,
            "queries": [
                {
                    "id": "q_test",
                    "name": "Test Query",
                    "pubmed_query": "CHO cells perfusion",
                    "enabled": True,
                }
            ],
        }
        test_queries_file.write_text(json.dumps(queries_content), encoding="utf-8")

        mock_summaries = [
            {
                "pmid": "11111",
                "title": "Perfusion bioreactors for CHO cells producing mAbs",
                "source_text": "High titer continuous bioprocessing.",
                "publication_date": "2026-01-01",
                "source": "pubmed",
            },
            {
                "pmid": "22222",
                "title": "Zebrafish embryo toxicity in wastewater",
                "source_text": "Heavy metal acute toxicity.",
                "publication_date": "2025-01-01",
                "source": "pubmed",
            },
        ]

        try:
            with patch("biolitagent.agents.literature_scout.search_pubmed", return_value=["11111", "22222"]), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", return_value=mock_summaries), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value={"11111": "Continuous bioprocess.", "22222": "Wastewater toxicity."}), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.generate_paraphrase") as mock_paraphrase, \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate") as mock_preflight:

                ret = run_literature_scout(
                    queries_path=test_queries_file,
                    state_path=test_state_file,
                    limit=2,
                    filter_only=True,
                )
                self.assertEqual(ret, 0)

                # Confirm NO LLM / paraphrase calls and NO pre-flight check
                mock_paraphrase.assert_not_called()
                mock_preflight.assert_not_called()

                # Confirm NO pending items written
                self.assertFalse(test_pending_file.exists())

                # Confirm filter_preview.jsonl was written with both candidates
                self.assertTrue(test_preview_file.exists())
                lines = test_preview_file.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 2)

                entry_pass = json.loads(lines[0])
                self.assertEqual(entry_pass["source_id"], "11111")
                self.assertTrue(entry_pass["passed"])
                self.assertIn("perfusion", entry_pass["anchor_matches"])
        finally:
            lit_module._FILTER_PREVIEW_FILE = orig_preview
            lit_module._OUTPUT_FILE = orig_output
            temp_dir.cleanup()

    def test_new_anchors_and_context_keywords(self):
        # Anchor terms: lactococcus, nissle, engineered bacteria
        for kw in ("lactococcus", "nissle", "engineered bacteria"):
            self.assertIn(kw, _BIOPROCESS_ANCHOR_KEYWORDS)
            is_rel, score, _, pos, _ = evaluate_bioprocess_relevance(f"Therapeutic application of {kw} in biomanufacturing")
            self.assertTrue(is_rel)
            self.assertIn(kw, pos)

        # Context term: recombinant (weight 1, does not pass alone)
        self.assertIn("recombinant", _BIOPROCESS_CONTEXT_KEYWORDS)
        self.assertEqual(_BIOPROCESS_CONTEXT_KEYWORDS["recombinant"], 1)
        is_rel_rec, score_rec, _, pos_rec, _ = evaluate_bioprocess_relevance("Recombinant expression study")
        self.assertFalse(is_rel_rec)  # 0 anchors -> filtered

    def test_key_and_email_validation(self):
        from biolitagent.agents.literature_scout import is_valid_ncbi_api_key, is_valid_ncbi_email

        self.assertFalse(is_valid_ncbi_api_key(None))
        self.assertFalse(is_valid_ncbi_api_key(""))
        self.assertFalse(is_valid_ncbi_api_key("your_api_key_here"))
        self.assertFalse(is_valid_ncbi_api_key("placeholder_key"))
        self.assertFalse(is_valid_ncbi_api_key("my_free_key"))
        self.assertTrue(is_valid_ncbi_api_key("a1b2c3d4e5f67890"))

        self.assertFalse(is_valid_ncbi_email(None))
        self.assertFalse(is_valid_ncbi_email(""))
        self.assertFalse(is_valid_ncbi_email("your.email@example.com"))
        self.assertFalse(is_valid_ncbi_email("placeholder@domain.com"))
        self.assertTrue(is_valid_ncbi_email("researcher@university.edu"))

    def test_mcp_probe_honesty_log(self):
        from biolitagent.agents.literature_scout import check_mcp_server_connection

        with patch("biolitagent.agents.literature_scout.shutil.which", return_value="npx"), \
             patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = b"10.2.0"
            mock_run.return_value = mock_proc

            with patch.dict(os.environ, {"NCBI_EMAIL": "valid@example.org", "NCBI_API_KEY": "valid_key"}):
                with self.assertLogs("literature_scout", level="INFO") as cm:
                    ok, status = check_mcp_server_connection("pubmed")
                    self.assertTrue(ok)
                    self.assertEqual(status, "READY")
                    log_text = "\n".join(cm.output)
                    self.assertIn("[MCP_PROBE_OK]", log_text)
                    self.assertNotIn("[MCP_CONNECTED]", log_text)

    def test_partial_failure_handling(self):
        # Two queries: Q1 succeeds, Q2 encounters NetworkFetchError (503).
        # Run must return exit code 2, write Q1 results, omit Q2 from seen_ids, and NOT log [NO_NEW_ITEMS] for Q2.
        from biolitagent.agents.literature_scout import NetworkFetchError

        temp_dir = tempfile.TemporaryDirectory()
        test_pending = Path(temp_dir.name) / "pending.jsonl"
        test_state = Path(temp_dir.name) / "state.json"
        test_queries = Path(temp_dir.name) / "queries.json"

        orig_pending = lit_module._OUTPUT_FILE
        lit_module._OUTPUT_FILE = test_pending

        queries_content = {
            "version": "1.1",
            "min_relevance_score": 2,
            "queries": [
                {"id": "q1", "name": "Success Query", "pubmed_query": "CHO perfusion", "enabled": True},
                {"id": "q2", "name": "Failed Query", "pubmed_query": "Chromatography error", "enabled": True},
            ],
        }
        test_queries.write_text(json.dumps(queries_content), encoding="utf-8")

        def mock_search(term, limit=15, sort="pub_date", **kwargs):
            if "Chromatography" in term:
                raise NetworkFetchError("HTTP 503 Service Unavailable", status_code=503)
            return ["1001"]

        mock_summaries = [{
            "pmid": "1001",
            "title": "Perfusion culture of CHO cells for mAb production",
            "source_text": "Continuous manufacturing bioreactor.",
            "publication_date": "2026-02-01",
            "source": "pubmed",
        }]

        try:
            with patch("biolitagent.agents.literature_scout.search_pubmed", side_effect=mock_search), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", return_value=mock_summaries), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value={"1001": "Bioreactor."}), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate", return_value=True), \
                 patch("biolitagent.agents.literature_scout.generate_paraphrase", return_value=("Original paraphrase.", "gemini")):

                exit_code = run_literature_scout(
                    queries_path=test_queries,
                    state_path=test_state,
                    dry_run=False,
                )
                self.assertEqual(exit_code, 2, "Expected exit code 2 for PARTIAL failure")

                # Q1 results were written
                self.assertTrue(test_pending.exists())
                pending_lines = test_pending.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(pending_lines), 1)
                rec = json.loads(pending_lines[0])
                self.assertEqual(rec["title"], "Perfusion culture of CHO cells for mAb production")
                self.assertEqual(rec["retrieval_method"], "rest")

                # State file contains Q1 PMID (1001), but NOT any failure artifacts
                state_data = json.loads(test_state.read_text(encoding="utf-8"))
                self.assertIn("1001", state_data["seen_ids"])
        finally:
            lit_module._OUTPUT_FILE = orig_pending
            temp_dir.cleanup()

    def test_live_run_top_3_and_llm_cap(self):
        # Query with 5 passing items: only top 3 should be sent to LLM.
        # When cap reached, fallback template is used.
        temp_dir = tempfile.TemporaryDirectory()
        test_pending = Path(temp_dir.name) / "pending_cap.jsonl"
        test_state = Path(temp_dir.name) / "state_cap.json"
        test_queries = Path(temp_dir.name) / "queries_cap.json"

        orig_pending = lit_module._OUTPUT_FILE
        lit_module._OUTPUT_FILE = test_pending

        queries_content = {
            "version": "1.1",
            "min_relevance_score": 2,
            "queries": [
                {"id": "q_cap", "name": "Cap Query", "pubmed_query": "CHO cells", "enabled": True},
            ],
        }
        test_queries.write_text(json.dumps(queries_content), encoding="utf-8")

        mock_summaries = [
            {"pmid": f"200{i}", "title": f"CHO cells perfusion study {i}", "source_text": "Bioreactor.", "publication_date": "2026-01-01", "source": "pubmed"}
            for i in range(1, 6)
        ]

        try:
            with patch("biolitagent.agents.literature_scout.search_pubmed", return_value=[f"200{i}" for i in range(1, 6)]), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", return_value=mock_summaries), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value={f"200{i}": "Bioreactor perfusion abstract." for i in range(1, 6)}), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate", return_value=True), \
                 patch("biolitagent.agents.literature_scout._MAX_RUN_LLM_CALLS", 1), \
                 patch("biolitagent.agents.literature_scout.generate_paraphrase", return_value=("Gemini summary.", "gemini")) as mock_para:

                exit_code = run_literature_scout(
                    queries_path=test_queries,
                    state_path=test_state,
                    dry_run=False,
                )
                self.assertEqual(exit_code, 0)

                # Only top 3 were processed
                pending_lines = test_pending.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(pending_lines), 3)

                # First item used gemini, remaining 2 hit the cap and used fallback template
                rec1 = json.loads(pending_lines[0])
                rec2 = json.loads(pending_lines[1])
                rec3 = json.loads(pending_lines[2])

                self.assertEqual(rec1["synthesis_method"], "gemini")
                self.assertEqual(rec2["synthesis_method"], "fallback_template")
                self.assertEqual(rec3["synthesis_method"], "fallback_template")
                self.assertEqual(mock_para.call_count, 1)
        finally:
            lit_module._OUTPUT_FILE = orig_pending
            temp_dir.cleanup()

    def test_allocate_llm_slots_fairness_and_guarantees(self):
        from biolitagent.agents.literature_scout import allocate_llm_slots, _GUARANTEED_QUERIES

        # Scenario: 5 queries with 3 items each (15 candidates total)
        # Q1: early_phase_cgmp_manufacturing (guaranteed)
        # Q2: other_1
        # Q3: expression_construct_troubleshooting (guaranteed)
        # Q4: microbiome_commensal_platform (guaranteed)
        # Q5: other_2
        candidates = {
            "early_phase_cgmp_manufacturing": [{"id": "e0"}, {"id": "e1"}, {"id": "e2"}],
            "other_1": [{"id": "o1_0"}, {"id": "o1_1"}, {"id": "o1_2"}],
            "expression_construct_troubleshooting": [{"id": "ex0"}, {"id": "ex1"}, {"id": "ex2"}],
            "microbiome_commensal_platform": [{"id": "m0"}, {"id": "m1"}, {"id": "m2"}],
            "other_2": [{"id": "o2_0"}, {"id": "o2_1"}, {"id": "o2_2"}],
        }
        order = [
            "other_1",
            "other_2",
            "early_phase_cgmp_manufacturing",
            "expression_construct_troubleshooting",
            "microbiome_commensal_platform",
        ]

        slots = allocate_llm_slots(candidates, order, max_calls=12)

        # 1. Cap is strictly 12
        self.assertEqual(len(slots), 12)

        # 2. All 3 guaranteed queries have at least their #1 item allocated
        for g_id in _GUARANTEED_QUERIES:
            self.assertIn((g_id, 0), slots)

        # 3. Round 0 items for all 5 queries are allocated
        for q_id in candidates:
            self.assertIn((q_id, 0), slots)

        # 4. Round 1 items: 5 queries have round 1 items -> 5 + 5 = 10 calls
        for q_id in candidates:
            self.assertIn((q_id, 1), slots)

        # 5. Round 2 items: only 2 remaining slots (10 + 2 = 12)
        # In order: other_1 gets round 2, other_2 gets round 2
        self.assertIn(("other_1", 2), slots)
        self.assertIn(("other_2", 2), slots)
        # Other queries do not get round 2 because cap of 12 was reached
        self.assertNotIn(("early_phase_cgmp_manufacturing", 2), slots)
        self.assertNotIn(("expression_construct_troubleshooting", 2), slots)
        self.assertNotIn(("microbiome_commensal_platform", 2), slots)

    def test_allocate_llm_slots_guarantee_when_budget_tight(self):
        from biolitagent.agents.literature_scout import allocate_llm_slots

        # If max_calls is only 3, guaranteed queries must take all 3 slots
        candidates = {
            "q_unrelated_1": [{"id": "u1_0"}],
            "q_unrelated_2": [{"id": "u2_0"}],
            "early_phase_cgmp_manufacturing": [{"id": "e0"}],
            "expression_construct_troubleshooting": [{"id": "ex0"}],
            "microbiome_commensal_platform": [{"id": "m0"}],
        }
        order = [
            "q_unrelated_1",
            "q_unrelated_2",
            "early_phase_cgmp_manufacturing",
            "expression_construct_troubleshooting",
            "microbiome_commensal_platform",
        ]
        slots = allocate_llm_slots(candidates, order, max_calls=3)
        self.assertEqual(len(slots), 3)
        self.assertIn(("early_phase_cgmp_manufacturing", 0), slots)
        self.assertIn(("expression_construct_troubleshooting", 0), slots)
        self.assertIn(("microbiome_commensal_platform", 0), slots)
        self.assertNotIn(("q_unrelated_1", 0), slots)
        self.assertNotIn(("q_unrelated_2", 0), slots)

    def test_end_of_run_llm_breakdown_printing(self):
        import io
        from contextlib import redirect_stdout

        temp_dir = tempfile.TemporaryDirectory()
        test_pending = Path(temp_dir.name) / "pending.jsonl"
        test_state = Path(temp_dir.name) / "state.json"
        test_queries = Path(temp_dir.name) / "queries.json"

        orig_pending = lit_module._OUTPUT_FILE
        lit_module._OUTPUT_FILE = test_pending

        queries_content = {
            "version": "1.1",
            "min_relevance_score": 2,
            "queries": [
                {"id": "early_phase_cgmp_manufacturing", "name": "Early Phase cGMP", "pubmed_query": "cGMP", "enabled": True},
            ],
        }
        test_queries.write_text(json.dumps(queries_content), encoding="utf-8")

        mock_summaries = [
            {"pmid": "3001", "title": "Scale-up and cGMP manufacturing of vaccine", "source_text": "Bioprocess.", "publication_date": "2026-01-01", "source": "pubmed"}
        ]

        buf = io.StringIO()
        try:
            with patch("biolitagent.agents.literature_scout.search_pubmed", return_value=["3001"]), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", return_value=mock_summaries), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value={"3001": "Bioprocess abstract."}), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate", return_value=True), \
                 patch("biolitagent.agents.literature_scout.generate_paraphrase", return_value=("Cached summary.", "dry_run_cache")), \
                 redirect_stdout(buf):

                exit_code = run_literature_scout(
                    queries_path=test_queries,
                    state_path=test_state,
                    dry_run=True,
                )
                self.assertEqual(exit_code, 0)
                out = buf.getvalue()
                self.assertIn("Synthesis Allocation: LLM calls used 1/12, fallback-template items 0", out)
                self.assertIn("Early Phase cGMP", out)
                self.assertIn("1 LLM, 0 fallback", out)
        finally:
            lit_module._OUTPUT_FILE = orig_pending
            temp_dir.cleanup()

    def test_item_e_must_pass_and_must_filter_fixtures(self):
        # 12 MUST PASS titles (tested on title alone)
        must_pass_titles = [
            "Optimization of multi-column chromatography for capture and polishing at high protein load",
            "Autonomous operation and quality monitoring of a continuous antibody downstream process",
            "The impacts of residence time and bed height on virus and aggregate clearance with a multimodal chromatography resin",
            "Genetic Divergence and Antibody Expression Influence the N-Glycomes of CHO-K1 and CHO-S Cells",
            "Alcohol-based solvents as mobile phases for LC-MS characterization of therapeutic proteins",
            "Soft-sensor model development for CHO growth/production, intracellular metabolite, and glycan predictions",
            "A roadmap for model-based bioprocess development",
            "Expectations for Phase-Appropriate Drug Substance and Drug Product Specifications for Early-Stage Protein Therapeutics",
            "GMP Manufacturing and Characterization of the HIV Booster Immunogen HxB2.WT.Core-C4b for Germline Targeting Vaccine Strategies",
            "Molecular chaperones and solubility tags: A 44-fold increase in recombinant fibEase yield for therapeutic applications",
            "Advances in refolding of proteins produced in E. coli",
            "Shortening the biologics clinical timeline with a novel method for generating stable, high-producing cell pools and clones",
        ]
        for title in must_pass_titles:
            is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(title)
            self.assertTrue(is_rel, f"Expected MUST PASS for '{title}', got is_rel={is_rel} (score={score}, pos={pos}, neg={neg})")
            self.assertGreaterEqual(score, 2, f"Score for '{title}' must be >= 2")
            anchors_in_pos = [k for k in pos if k in _BIOPROCESS_ANCHOR_KEYWORDS or k == "cho (case-sensitive)"]
            self.assertTrue(len(anchors_in_pos) > 0, f"Expected at least one anchor in pos for '{title}', got {pos}")

        # 7 MUST FILTER titles (tested on title alone)
        must_filter_titles = [
            "Addition of polyethylene glycol 6000 improves the sensitivity of the protein A plaque assay for detection of human immunoglobulin secreting cells",
            "[Protein A immunoadsorption treatment of patients with refractory autoimmune thrombopenia]",
            "Physiologically Based Biopharmaceutic Lung Deposition Modeling to Guide Clinical Device Transition of Protein A from a Nebulizer to a Dry Powder Inhaler",
            "Deciphering the characteristics of strong-flavor Daqu at different grades through integrated microbiome and metabolome analysis",
            "Assessment of Stability of Preservation Techniques for Strawberry Soil Microbiomes",
            "Biosynthesis of vanillin glucoside in Escherichia coli",
            "Dynamic Pareto Optimization of Consolidated Bioprocessing for Ethanol Titer",
        ]
        for title in must_filter_titles:
            is_rel, score, match_pct, pos, neg = evaluate_bioprocess_relevance(title)
            self.assertFalse(is_rel, f"Expected MUST FILTER for '{title}', got is_rel={is_rel} (score={score}, pos={pos}, neg={neg})")

    def test_abstract_scoring_multiplier_and_cap(self):
        # Title only: "perfusion" (anchor, weight 2) -> title score = 2 * 2 = 4
        is_rel_title, score_title, _, _, _ = evaluate_bioprocess_relevance("Perfusion study")
        self.assertEqual(score_title, 4)

        # Title with 1 anchor (weight 2 * 2 = 4) + abstract with multiple anchors
        # Abstract raw score = 2 + 2 + 2 + 2 = 8, capped at _ABSTRACT_SCORE_CAP = 6
        # Total score = 4 + 6 = 10
        is_rel_both, score_both, _, pos_both, _ = evaluate_bioprocess_relevance(
            title="Perfusion cell culture",
            abstract_text="Continuous manufacturing in a stirred-tank bioreactor using tangential flow filtration and chromatography."
        )
        self.assertTrue(is_rel_both)
        self.assertEqual(score_both, 10)

    def test_source_basis_and_title_only_guard(self):
        from biolitagent.agents.literature_scout import _build_record

        # 1. Record schema includes source_basis and never persists abstract text
        rec_abstract = _build_record(
            item={"title": "Test Title", "_transient_abstract": "Some secret abstract"},
            description="Synthesis description",
            query_id="q1",
            index_url="https://ncbi.nlm.nih.gov",
            source_basis="title_and_abstract",
        )
        self.assertEqual(rec_abstract["source_basis"], "title_and_abstract")
        self.assertNotIn("_transient_abstract", rec_abstract)
        self.assertNotIn("abstract", rec_abstract)

        rec_title = _build_record(
            item={"title": "Test Title 2"},
            description="Fallback description",
            query_id="q1",
            index_url="https://ncbi.nlm.nih.gov",
            synthesis_method="fallback_template",
            source_basis="title_only",
        )
        self.assertEqual(rec_title["source_basis"], "title_only")
        self.assertEqual(rec_title["synthesis_method"], "fallback_template")

        # 2. generate_paraphrase does NOT call Gemini if source_basis is title_only
        mock_client = MagicMock()
        with patch("biolitagent.agents.literature_scout._get_llm_client", return_value=mock_client):
            desc, method = lit_module.generate_paraphrase(
                {"title": "Title Only Candidate", "source_basis": "title_only"},
                query_id="q1",
                dry_run=False,
            )
            self.assertEqual(method, "fallback_template")
            mock_client.models.generate_content.assert_not_called()

    def test_seven_word_verbatim_overlap_guard(self):
        from biolitagent.agents.literature_scout import check_7word_overlap

        abstract = "The continuous perfusion of mammalian CHO cells demonstrated superior volumetric productivity under controlled dissolved oxygen."
        overlap_para = "This process shows that the continuous perfusion of mammalian CHO cells demonstrated superior yield."
        clean_para = "Perfusion operations achieved elevated productivity when oxygen levels were maintained precisely."

        self.assertTrue(check_7word_overlap(overlap_para, abstract))
        self.assertFalse(check_7word_overlap(clean_para, abstract))

        # Test that generate_paraphrase falls back to template when 7+ word verbatim overlap is produced
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = overlap_para
        mock_client.models.generate_content.return_value = mock_response

        with patch("biolitagent.agents.literature_scout._get_llm_client", return_value=mock_client), \
             patch("biolitagent.agents.literature_scout.record_call"):
            item = {
                "title": "Perfusion CHO study",
                "_transient_abstract": abstract,
                "source_basis": "title_and_abstract",
            }
            desc, method = lit_module.generate_paraphrase(item, query_id="q1", dry_run=False)
            self.assertEqual(method, "fallback_template")
            self.assertIn("Investigation into perfusion cho study", desc)

    def test_batched_efetch_xml_parsing(self):
        from biolitagent.agents.literature_scout import fetch_pubmed_abstracts

        sample_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2026//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_260101.dtd">
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>888001</PMID>
                    <Article>
                        <Abstract>
                            <AbstractText Label="BACKGROUND">Continuous perfusion cell culture offers high volumetric yield.</AbstractText>
                            <AbstractText Label="RESULTS">Titer improved 3-fold using N-1 perfusion seed trains.</AbstractText>
                            <AbstractText Label="CONCLUSIONS">Process intensification was achieved.</AbstractText>
                        </Abstract>
                    </Article>
                </MedlineCitation>
            </PubmedArticle>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>888002</PMID>
                    <Article>
                        <Abstract>
                            <AbstractText>Unstructured abstract text for downstream chromatography purification.</AbstractText>
                        </Abstract>
                    </Article>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>
        """
        with patch("biolitagent.agents.literature_scout._http_get_bytes", return_value=sample_xml):
            abstract_map = fetch_pubmed_abstracts(["888001", "888002"])
            self.assertEqual(len(abstract_map), 2)
            self.assertIn("BACKGROUND: Continuous perfusion", abstract_map["888001"])
            self.assertIn("RESULTS: Titer improved 3-fold", abstract_map["888001"])
            self.assertEqual(abstract_map["888002"], "Unstructured abstract text for downstream chromatography purification.")

    def test_vaccine_modality_cooccurrence_guard(self):
        # 1. Unpaired VLP paper without any process/manufacturing terms -> demoted to context -> 0 anchors -> FILTERED
        unpaired_vlp = "Immunogenicity and protective efficacy of a novel VLP candidate in mouse models"
        is_rel_u, score_u, _, pos_u, _ = evaluate_bioprocess_relevance(unpaired_vlp)
        self.assertFalse(is_rel_u)
        self.assertIn("vlp (unpaired)", pos_u)
        self.assertNotIn("vlp", [k for k in pos_u if k in _BIOPROCESS_ANCHOR_KEYWORDS])

        # 2. Paired VLP paper with process terms (e.g. purification, yield, chromatography) -> passes as anchor
        paired_vlp = "Downstream purification and yield optimization of virus-like particles using multimodal chromatography"
        is_rel_p, score_p, _, pos_p, _ = evaluate_bioprocess_relevance(paired_vlp)
        self.assertTrue(is_rel_p)
        self.assertIn("virus-like particle", pos_p)
        self.assertGreaterEqual(score_p, 4)

        # 3. Unpaired OMV paper without process terms -> demoted to context -> FILTERED
        unpaired_omv = "Proteomic characterization of bacterial outer membrane vesicles in host-pathogen interactions"
        is_rel_o, score_o, _, pos_o, _ = evaluate_bioprocess_relevance(unpaired_omv)
        self.assertFalse(is_rel_o)
        self.assertIn("outer membrane vesicle (unpaired)", pos_o)

        # 4. Paired OMV paper with fermentation and scale-up -> passes as anchor
        paired_omv = "Scale-up of high-cell-density fermentation for outer membrane vesicle production in bioreactors"
        is_rel_po, score_po, _, pos_po, _ = evaluate_bioprocess_relevance(paired_omv)
        self.assertTrue(is_rel_po)
        self.assertIn("outer membrane vesicle", pos_po)
        self.assertIn("bioreactor", pos_po)

    def test_normalize_title_for_dedupe(self):
        from biolitagent.agents.literature_scout import _normalize_title_for_dedupe

        self.assertEqual(_normalize_title_for_dedupe(""), "")
        self.assertEqual(_normalize_title_for_dedupe(None), "")
        self.assertEqual(
            _normalize_title_for_dedupe("Continuous Chromatography for mAb Purification."),
            "continuous chromatography for mab purification",
        )
        self.assertEqual(
            _normalize_title_for_dedupe("  Continuous   Chromatography-for (mAb) Purification! \n"),
            "continuous chromatographyfor mab purification",
        )

    def test_cross_query_deduplication_prefers_llm(self):
        """Cross-query deduplication should keep LLM synthesis over fallback template for the same PMID."""
        from biolitagent.agents.literature_scout import _normalize_title_for_dedupe

        temp_dir = tempfile.TemporaryDirectory()
        orig_pending = lit_module._OUTPUT_FILE
        try:
            test_queries = Path(temp_dir.name) / "queries.json"
            test_state = Path(temp_dir.name) / "literature_state.json"
            test_pending = Path(temp_dir.name) / "pending_items.jsonl"
            lit_module._OUTPUT_FILE = test_pending

            # Q1 is not guaranteed, Q2 is guaranteed
            queries_content = {
                "version": "1.1",
                "min_relevance_score": 2,
                "queries": [
                    {"id": "other_query", "name": "Other Query", "pubmed_query": "mAb", "enabled": True},
                    {"id": "early_phase_cgmp_manufacturing", "name": "Guaranteed Query", "pubmed_query": "cGMP", "enabled": True},
                ],
            }
            test_queries.write_text(json.dumps(queries_content), encoding="utf-8")

            # Both queries return the exact same paper (PMID 99901)
            shared_summary = {
                "pmid": "99901",
                "title": "Continuous purification of mAb in perfusion bioreactor",
                "source_text": "Bioreactor.",
                "publication_date": "2026-01-01",
                "source": "pubmed",
            }
            abstracts = {"99901": "Continuous chromatography and perfusion bioreactor for mAb purification."}

            def mock_search(query_str, limit=None, sort=None, pub_window_years=None):
                return ["99901"]

            def mock_fetch(pmids):
                return [shared_summary]

            with patch("biolitagent.agents.literature_scout.search_pubmed", side_effect=mock_search), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", side_effect=mock_fetch), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value=abstracts), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate", return_value=True), \
                 patch("biolitagent.agents.literature_scout._MAX_RUN_LLM_CALLS", 1), \
                 patch("biolitagent.agents.literature_scout.generate_paraphrase", return_value=("Gemini synthesized summary.", "gemini")):

                exit_code = run_literature_scout(
                    queries_path=test_queries,
                    state_path=test_state,
                    dry_run=False,
                )
                self.assertEqual(exit_code, 0)

                pending_lines = test_pending.read_text(encoding="utf-8").strip().splitlines()
                # Must be deduplicated: exactly 1 item written, not 2
                self.assertEqual(len(pending_lines), 1)

                rec = json.loads(pending_lines[0])
                # The LLM synthesis from guaranteed query replaced the fallback template from other_query
                self.assertEqual(rec["synthesis_method"], "gemini")
                self.assertEqual(rec["description"], "Gemini synthesized summary.")

                # State records PMID as seen
                state = json.loads(test_state.read_text(encoding="utf-8"))
                self.assertIn("99901", state["seen_ids"])
        finally:
            lit_module._OUTPUT_FILE = orig_pending
            temp_dir.cleanup()

    def test_cross_query_deduplication_by_normalized_title(self):
        """Cross-query deduplication matches identical normalized titles across queries."""
        temp_dir = tempfile.TemporaryDirectory()
        orig_pending = lit_module._OUTPUT_FILE
        try:
            test_queries = Path(temp_dir.name) / "queries.json"
            test_state = Path(temp_dir.name) / "literature_state.json"
            test_pending = Path(temp_dir.name) / "pending_items.jsonl"
            lit_module._OUTPUT_FILE = test_pending

            queries_content = {
                "version": "1.1",
                "min_relevance_score": 2,
                "queries": [
                    {"id": "q1", "name": "Query 1", "pubmed_query": "mAb", "enabled": True},
                    {"id": "q2", "name": "Query 2", "pubmed_query": "mAb", "enabled": True},
                ],
            }
            test_queries.write_text(json.dumps(queries_content), encoding="utf-8")

            # Slightly different titles and PMIDs that normalize to the same title
            rec1 = {"pmid": "8001", "title": "Perfusion culture of CHO cells for mAb production.", "source_text": "Bio.", "publication_date": "2026-01-01", "source": "pubmed"}
            rec2 = {"pmid": "8002", "title": "Perfusion culture of CHO cells for mAb production", "source_text": "Bio.", "publication_date": "2026-01-01", "source": "pubmed"}

            def mock_search(query_str, limit=None, sort=None, pub_window_years=None):
                return ["8001"] if "Query 1" in str(query_str) or query_str == "mAb" else ["8002"]

            # Alternate returning rec1 for first call, rec2 for second call
            call_count = [0]
            def mock_fetch(pmids):
                call_count[0] += 1
                return [rec1] if call_count[0] == 1 else [rec2]

            with patch("biolitagent.agents.literature_scout.search_pubmed", side_effect=lambda q, **kw: ["8001"] if call_count[0] == 0 else ["8002"]), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_summaries", side_effect=mock_fetch), \
                 patch("biolitagent.agents.literature_scout.fetch_pubmed_abstracts", return_value={"8001": "Bioprocess.", "8002": "Bioprocess."}), \
                 patch("biolitagent.agents.literature_scout.check_mcp_server_connection", return_value=(False, "mcp_down")), \
                 patch("biolitagent.agents.literature_scout.check_preflight_gate", return_value=True), \
                 patch("biolitagent.agents.literature_scout._MAX_RUN_LLM_CALLS", 0):  # Both use fallback

                exit_code = run_literature_scout(
                    queries_path=test_queries,
                    state_path=test_state,
                    dry_run=False,
                )
                self.assertEqual(exit_code, 0)

                pending_lines = test_pending.read_text(encoding="utf-8").strip().splitlines()
                # Deduplicated to 1 item despite different PMIDs
                self.assertEqual(len(pending_lines), 1)
        finally:
            lit_module._OUTPUT_FILE = orig_pending
            temp_dir.cleanup()

    def test_pdf_title_artifact_detection_and_fallback(self):
        from biolitagent.agents.pdf_ingestion import _is_filename_or_artifact_title, _extract_fallback_title

        # 1. Detection of artifact titles
        self.assertTrue(_is_filename_or_artifact_title("fbioe-2021-796991 1..9"))
        self.assertTrue(_is_filename_or_artifact_title("fbioe-2021-796991"))
        self.assertTrue(_is_filename_or_artifact_title("fbioe-2021-796991 1-9"))
        self.assertTrue(_is_filename_or_artifact_title("manuscript_v2.pdf"))
        self.assertTrue(_is_filename_or_artifact_title("untitled"))
        self.assertTrue(_is_filename_or_artifact_title("1..9"))
        self.assertTrue(_is_filename_or_artifact_title(""))
        self.assertTrue(_is_filename_or_artifact_title(None))

        # Real scientific titles are not artifacts
        self.assertFalse(_is_filename_or_artifact_title("HEK293 Cell Line as a Platform to Produce Recombinant Proteins"))
        self.assertFalse(_is_filename_or_artifact_title("Continuous Downstream Processing of Monoclonal Antibodies"))

        # 2. Fallback title extraction from first-page text
        raw_text = (
            "Frontiers in Bioengineering and Biotechnology\n"
            "ORIGINAL RESEARCH\n"
            "doi: 10.3389/fbioe.2021.796991\n"
            "HEK293 Cell Line as a Platform to Produce\n"
            "Recombinant Proteins and Viral Vectors.\n"
            "Jane Doe, John Smith\n"
            "Department of Biotechnology, University of Science\n"
        )
        resolved_title, is_flagged = _extract_fallback_title(raw_text, Path("fbioe-2021-796991.pdf"))
        self.assertFalse(is_flagged)
        self.assertEqual(resolved_title, "HEK293 Cell Line as a Platform to Produce Recombinant Proteins and Viral Vectors.")

        # 3. Fallback when text has no usable title lines falls back to cleaned stem
        empty_text = "doi: 10.1234/test\nUniversity of Science"
        resolved_title2, is_flagged2 = _extract_fallback_title(
            empty_text,
            Path("R HEK293 Cell Line as a Platform to Produce Recombinant.pdf")
        )
        self.assertFalse(is_flagged2)
        self.assertEqual(resolved_title2, "HEK293 Cell Line as a Platform to Produce Recombinant")


if __name__ == "__main__":
    unittest.main()


