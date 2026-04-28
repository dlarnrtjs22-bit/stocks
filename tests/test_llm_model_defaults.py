from __future__ import annotations

import unittest

import chatgpt
from batch.runtime_source import chatgpt as runtime_chatgpt
from batch.runtime_source.engine import llm_analyzer


class LlmModelDefaultsTest(unittest.TestCase):
    def test_default_codex_model_is_gpt_55(self) -> None:
        self.assertEqual("gpt-5.5", chatgpt.DEFAULT_CODEX_MODEL)
        self.assertEqual("gpt-5.5", runtime_chatgpt.DEFAULT_CODEX_MODEL)
        self.assertEqual("gpt-5.5", llm_analyzer.DEFAULT_CODEX_MODEL)


if __name__ == "__main__":
    unittest.main()
