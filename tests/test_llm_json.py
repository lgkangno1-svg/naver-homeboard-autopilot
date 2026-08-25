import unittest

import llm


class JsonObjectCoercionTests(unittest.TestCase):
    def test_dict_is_kept(self):
        value = {"title": "테스트", "sections": []}
        self.assertEqual(llm._coerce_single_json_object(value), value)

    def test_single_object_array_is_unwrapped(self):
        value = [{"title": "테스트", "sections": []}]
        self.assertEqual(
            llm._coerce_single_json_object(value),
            {"title": "테스트", "sections": []},
        )

    def test_multi_object_array_is_rejected(self):
        with self.assertRaises(ValueError):
            llm._coerce_single_json_object([{"a": 1}, {"b": 2}])

    def test_non_object_json_is_rejected(self):
        with self.assertRaises(ValueError):
            llm._coerce_single_json_object(["not-an-object"])


if __name__ == "__main__":
    unittest.main()
