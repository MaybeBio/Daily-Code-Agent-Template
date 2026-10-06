"""
tests/test_review_provenance.py
-------------------------------
Unit tests verifying review checkpoint provenance metadata, approval_runs schema,
model_name null handling for fallback templates, and review badge displays.
"""

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biolitagent.agents.review_checkpoint import (
    create_run_record,
    load_taxonomy,
    open_db,
    print_item,
    print_overview,
    suggest_tag,
    update_run_record,
    write_approved,
)


class TestReviewProvenance(unittest.TestCase):
    def test_review_checkpoint_suggest_tag_weights(self):
        tax_path = Path("biolitagent/config/chapter_taxonomy.json")
        if not tax_path.exists():
            tax_path = Path("../biolitagent/config/chapter_taxonomy.json")
        taxonomy = load_taxonomy(tax_path)

        # Generic word "optimization" without bioprocess anchors -> no tag
        generic_item = {
            "title": "Optimization of general algorithmic pipelines",
            "description": "Mathematical parameter tuning.",
        }
        tag = suggest_tag(generic_item, taxonomy)
        self.assertIsNone(tag)

        # Process anchors: "digital twin" + "bioreactor" -> hybrid_modeling
        digital_twin_item = {
            "title": "Development of a digital twin for bioreactor monitoring",
            "description": "Hybrid modeling of cell culture dynamics.",
        }
        tag = suggest_tag(digital_twin_item, taxonomy)
        self.assertEqual(tag, "hybrid_modeling")

    def test_approval_runs_reviewer_and_provenance_metadata(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "test_knowledge.db"

        try:
            conn = open_db(db_path)
            cursor = conn.execute("PRAGMA table_info(approval_runs)")
            cols = [row[1] for row in cursor.fetchall()]
            self.assertIn("reviewer", cols)

            run_id = "test-run-123"
            create_run_record(conn, run_id, reviewer="alice_reviewer")
            row = conn.execute("SELECT reviewer FROM approval_runs WHERE run_id = ?", (run_id,)).fetchone()
            self.assertEqual(row["reviewer"], "alice_reviewer")

            item = {
                "id": "pending-item-1",
                "title": "Fed-batch culture of CHO cells",
                "description": "Bioprocess description.",
                "source_type": "literature",
                "chapter_tag": "upstream_process",
                "synthesis_method": "gemini",
                "model_name": "gemini-2.5-flash",
            }
            write_approved([item], run_id, conn, reviewer="alice_reviewer")

            item_row = conn.execute("SELECT metadata_json FROM knowledge_items WHERE pending_id = 'pending-item-1'").fetchone()
            self.assertIsNotNone(item_row)
            meta = json.loads(item_row["metadata_json"])
            self.assertEqual(meta["model_name"], "gemini-2.5-flash")
            self.assertIn("config_versions", meta)
            self.assertEqual(meta["reviewer"], "alice_reviewer")
            self.assertEqual(meta["config_versions"]["taxonomy_version"], "1.1")
            self.assertEqual(meta["config_versions"]["queries_version"], "1.1")

            update_run_record(conn, run_id, approved=1, rejected=0, skipped=0, reviewer="alice_reviewer")
            updated_row = conn.execute("SELECT items_approved, reviewer FROM approval_runs WHERE run_id = ?", (run_id,)).fetchone()
            self.assertEqual(updated_row["items_approved"], 1)
            self.assertEqual(updated_row["reviewer"], "alice_reviewer")
            conn.close()
        finally:
            temp_dir.cleanup()

    def test_model_name_null_handling_for_fallback_template(self):
        # When synthesis_method is fallback_template, model_name must be None (null in json)
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "test_knowledge_null.db"

        try:
            conn = open_db(db_path)
            run_id = "run-null-model-test"
            create_run_record(conn, run_id, reviewer="reviewer_bob")

            # 1. Fallback template item
            fallback_item = {
                "id": "item-fallback-1",
                "title": "Perfusion of Mammalian Cells",
                "description": "Templated fallback description.",
                "source_type": "literature",
                "chapter_tag": "upstream_process",
                "synthesis_method": "fallback_template",
                "model_name": None,
            }

            # 2. Gemini synthesis item
            gemini_item = {
                "id": "item-gemini-1",
                "title": "Continuous Chromatography of mAbs",
                "description": "Gemini generated synthesis.",
                "source_type": "literature",
                "chapter_tag": "downstream_process",
                "synthesis_method": "gemini",
                "model_name": "gemini-2.5-flash",
            }

            write_approved([fallback_item, gemini_item], run_id, conn, reviewer="reviewer_bob")

            # Check fallback record
            row_fb = conn.execute("SELECT metadata_json FROM knowledge_items WHERE pending_id = 'item-fallback-1'").fetchone()
            meta_fb = json.loads(row_fb["metadata_json"])
            self.assertIsNone(meta_fb["model_name"])
            self.assertEqual(meta_fb["synthesis_method"], "fallback_template")

            # Check gemini record
            row_gm = conn.execute("SELECT metadata_json FROM knowledge_items WHERE pending_id = 'item-gemini-1'").fetchone()
            meta_gm = json.loads(row_gm["metadata_json"])
            self.assertEqual(meta_gm["model_name"], "gemini-2.5-flash")
            self.assertEqual(meta_gm["synthesis_method"], "gemini")

            conn.close()
        finally:
            temp_dir.cleanup()

    def test_review_checkpoint_template_marker(self):
        item = {
            "title": "Aseptic Processing in Biomanufacturing",
            "source_type": "literature",
            "chapter_tag": "facility_aseptic",
            "description": "Analysis of cleanroom protocols.",
            "synthesis_method": "fallback_template",
            "detected_at": "2026-03-26T12:00:00Z",
        }

        captured_output = io.StringIO()
        with patch("sys.stdout", captured_output):
            print_item(item, 1, 1)

        output_str = captured_output.getvalue()
        self.assertIn("[TEMPLATE] Analysis of cleanroom protocols.", output_str)

    def test_review_badges_and_sorting(self):
        tag_order = {"tag_a": 0, "tag_b": 1}
        items_to_sort = [
            ("tag_a", {"title": "Paper 1 (stale, high)", "stale": True, "match_percentage": 90.0, "recency_bonus": 0.0}),
            ("tag_a", {"title": "Paper 2 (fresh, med)", "stale": False, "match_percentage": 60.0, "recency_bonus": 1.0}),
            ("tag_a", {"title": "Paper 3 (fresh, high)", "stale": False, "match_percentage": 85.0, "recency_bonus": 2.0}),
            ("tag_b", {"title": "Paper 4 (tag b)", "stale": False, "match_percentage": 70.0, "recency_bonus": 0.5}),
        ]

        def _sort_key(tp):
            tag, item = tp
            tag_idx = tag_order.get(tag or "", 9999)
            is_stale = 1 if item.get("stale") is True else 0
            match_pct = float(item.get("match_percentage") or 0.0)
            recency = float(item.get("recency_bonus") or 0.0)
            composite = match_pct + recency
            title = item.get("title") or ""
            return (tag_idx, is_stale, -composite, title)

        sorted_items = sorted(items_to_sort, key=_sort_key)
        sorted_titles = [item["title"] for _, item in sorted_items]

        expected_titles = [
            "Paper 3 (fresh, high)",
            "Paper 2 (fresh, med)",
            "Paper 1 (stale, high)",
            "Paper 4 (tag b)",
        ]
        self.assertEqual(sorted_titles, expected_titles)

        overview_output = io.StringIO()
        with patch("sys.stdout", overview_output):
            print_overview(
                [
                    ("tag_a", {"title": "Fresh Paper", "stale": False, "match_percentage": 85.2}),
                    ("tag_a", {"title": "Stale Paper", "stale": True, "match_percentage": 60.0}),
                ],
                [{"id": "tag_a", "label": "Tag A"}],
            )
        ov_text = overview_output.getvalue()
        self.assertIn("(85%)", ov_text)
        self.assertIn("(60%) [STALE]", ov_text)


if __name__ == "__main__":
    unittest.main()
