from __future__ import annotations

import unittest

from app.db.base import Base
import app.models  # noqa: F401


class DatabaseModelTests(unittest.TestCase):
    def test_initial_platform_schema_tables_are_registered(self) -> None:
        tables = set(Base.metadata.tables)

        self.assertIn("platform_users", tables)
        self.assertIn("tenants", tables)
        self.assertIn("customer_apps", tables)
        self.assertIn("ai_providers", tables)
        self.assertIn("ai_api_keys", tables)
        self.assertIn("llm_rotation_pools", tables)
        self.assertIn("llm_model_profiles", tables)
        self.assertNotIn("embedding_rotation_pools", tables)
        self.assertIn("embedding_model_profiles", tables)
        self.assertIn("ai_usage_events", tables)

    def test_only_llm_keeps_rotation_state(self) -> None:
        llm_columns = set(Base.metadata.tables["llm_model_profiles"].columns.keys())
        embedding_columns = set(Base.metadata.tables["embedding_model_profiles"].columns.keys())
        llm_pool_columns = set(Base.metadata.tables["llm_rotation_pools"].columns.keys())

        self.assertIn("max_output_tokens", llm_columns)
        self.assertIn("top_p", llm_columns)
        self.assertIn("embedding_dimensions", embedding_columns)
        self.assertIn("batch_size", embedding_columns)
        self.assertNotIn("today_quota_exhausted", llm_columns)
        self.assertNotIn("today_quota_exhausted", embedding_columns)
        self.assertIn("profile_id", llm_pool_columns)
        self.assertIn("current_position", llm_pool_columns)
        self.assertIn("today_quota_exhausted", llm_pool_columns)
        self.assertIn("rate_limited_until", llm_pool_columns)

    def test_api_key_hash_is_not_unique(self) -> None:
        key_hash_column = Base.metadata.tables["ai_api_keys"].columns["key_hash"]

        self.assertFalse(key_hash_column.unique)

    def test_document_registry_allows_unscoped_rows_and_guards_filename_duplicates(self) -> None:
        documents = Base.metadata.tables["documents"]
        unique_constraints = {
            constraint.name
            for constraint in documents.constraints
            if constraint.name
        }

        self.assertTrue(documents.columns["tenant_id"].nullable)
        self.assertTrue(documents.columns["app_id"].nullable)
        self.assertIn("uq_documents_filename", unique_constraints)


if __name__ == "__main__":
    unittest.main()
