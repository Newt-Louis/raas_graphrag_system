from __future__ import annotations

import unittest

from app.api.v1.test_api_ai_key import _litellm_model_name
from app.models.ai_gateway import AIProvider


class TestAPIAIKeyEndpointTests(unittest.TestCase):
    def test_litellm_model_name_prefixes_provider_code(self) -> None:
        provider = AIProvider(code="gemini", display_name="Gemini")

        self.assertEqual(
            _litellm_model_name(provider, "gemini-2.0-flash"),
            "gemini/gemini-2.0-flash",
        )

    def test_litellm_model_name_does_not_double_prefix_existing_provider_code(self) -> None:
        provider = AIProvider(code="gemini", display_name="Gemini")

        self.assertEqual(
            _litellm_model_name(provider, "gemini/gemini-2.0-flash"),
            "gemini/gemini-2.0-flash",
        )


if __name__ == "__main__":
    unittest.main()
