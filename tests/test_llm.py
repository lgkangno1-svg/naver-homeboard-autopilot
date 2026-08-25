import unittest
from unittest.mock import Mock, patch

import llm


class OpenCodeGoResilienceTests(unittest.TestCase):
    def test_go_candidates_are_deduplicated(self):
        candidates = llm._go_candidates("write")
        self.assertTrue(candidates)
        self.assertEqual(candidates[0], llm.OPENCODE_GO_MODEL)
        self.assertEqual(len(candidates), len(set(candidates)))

    def test_review_candidates_start_with_review_model(self):
        candidates = llm._go_candidates("review")
        self.assertTrue(candidates)
        self.assertEqual(candidates[0], llm.OPENCODE_GO_REVIEW_MODEL)

    def test_go_request_omits_temperature_by_default(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        with patch("llm.requests.post", return_value=response) as post:
            old_key = llm.OPENCODE_GO_KEY
            try:
                llm.OPENCODE_GO_KEY = "test-key"
                out = llm._post_opencode_go(
                    [{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    temperature=0.7,
                    timeout=3,
                    model="mimo-v2.5",
                )
            finally:
                llm.OPENCODE_GO_KEY = old_key
        self.assertEqual(out, "OK")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "mimo-v2.5")
        self.assertFalse(payload["stream"])
        if not llm.OPENCODE_GO_SEND_TEMPERATURE:
            self.assertNotIn("temperature", payload)

    def test_go_error_includes_provider_body(self):
        response = Mock()
        response.status_code = 400
        response.text = '{"error":{"message":"Model is unavailable"}}'
        response.reason = "Bad Request"
        with patch("llm.requests.post", return_value=response):
            with self.assertRaises(RuntimeError) as cm:
                llm._post_opencode_go(
                    [{"role": "user", "content": "hi"}],
                    max_tokens=100,
                    temperature=0.7,
                    timeout=3,
                    model="kimi-k3",
                )
        msg = str(cm.exception)
        self.assertIn("HTTP 400", msg)
        self.assertIn("Model is unavailable", msg)
        self.assertIn("kimi-k3", msg)


if __name__ == "__main__":
    unittest.main()
