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
        self.assertIn("embedding_rotation_pools", tables)
        self.assertIn("embedding_model_profiles", tables)
        self.assertIn("ai_usage_events", tables)

    def test_llm_and_embedding_rotation_state_is_separated(self) -> None:
        llm_columns = set(Base.metadata.tables["llm_model_profiles"].columns.keys())
        embedding_columns = set(Base.metadata.tables["embedding_model_profiles"].columns.keys())

        self.assertIn("max_output_tokens", llm_columns)
        self.assertIn("top_p", llm_columns)
        self.assertIn("embedding_dimensions", embedding_columns)
        self.assertIn("batch_size", embedding_columns)
        self.assertIn("today_quota_exhausted", llm_columns)
        self.assertIn("today_quota_exhausted", embedding_columns)
        self.assertIn("rate_limited_until", llm_columns)
        self.assertIn("rate_limited_until", embedding_columns)


if __name__ == "__main__":
    unittest.main()
