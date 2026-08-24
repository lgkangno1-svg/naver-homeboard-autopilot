import json
import os
import tempfile
import unittest

import publish_guard
import writer_v2


class QualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", encoding="utf-8") as f:
            cls.cfg = json.load(f)

    def _post(self, intro):
        para = "생활비를 줄일 때는 가격 하나보다 조건과 사용 빈도를 같이 보는 편이 좋습니다. " * 8
        return {
            "title": "통신비 절약 전에 먼저 확인할 3가지 조건은?",
            "intro": [intro, para],
            "sections": [
                {"heading": "첫 번째로 볼 조건", "paragraphs": [para], "emphasis": "조건을 먼저 비교합니다.", "centered_lines": []},
                {"heading": "두 번째로 볼 조건", "paragraphs": [para], "emphasis": "총비용을 확인합니다.", "centered_lines": []},
                {"heading": "마지막으로 볼 조건", "paragraphs": [para], "emphasis": "해지 조건도 확인합니다.", "centered_lines": []}
            ],
            "conclusion": [para],
            "image_queries": ["휴대폰 요금 명세서", "통신비 비교"]
        }

    def test_fake_experience_is_rejected(self):
        post = self._post("제가 직접 3개월 사용해 보니 통신비가 줄었습니다.")
        issues = writer_v2._deterministic_issues(post, self.cfg)
        self.assertTrue(any("체험" in issue or "사용기간" in issue for issue in issues))

    def test_plain_informational_copy_does_not_trigger_fake_experience(self):
        post = self._post("통신비 절약을 고민한다면 먼저 약정과 데이터 사용량을 확인해야 합니다.")
        issues = writer_v2._deterministic_issues(post, self.cfg)
        self.assertFalse(any("체험" in issue or "사용기간" in issue for issue in issues))

    def test_content_id_is_stable(self):
        post = self._post("통신비 절약은 현재 요금제부터 확인하는 것이 시작입니다.")
        self.assertEqual(publish_guard.content_id(post), publish_guard.content_id(post))


class SlotCountingTests(unittest.TestCase):
    def test_draft_and_publish_slots_are_separate(self):
        old_log = publish_guard.LOG
        try:
            with tempfile.TemporaryDirectory() as td:
                publish_guard.LOG = os.path.join(td, "published.jsonl")
                from datetime import datetime
                from zoneinfo import ZoneInfo
                today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
                rows = [
                    {"ts": today + "T09:11:00+09:00", "mode": "draft", "status": "draft", "slot_id": today + "T09:10"},
                    {"ts": today + "T12:31:00+09:00", "mode": "publish", "status": "published", "slot_id": today + "T12:30"},
                    {"ts": today + "T18:41:00+09:00", "mode": "publish", "status": "uncertain", "slot_id": today + "T18:40"}
                ]
                with open(publish_guard.LOG, "w", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                self.assertEqual(publish_guard.today_slot_count("draft"), 1)
                self.assertEqual(publish_guard.today_slot_count("publish"), 2)
        finally:
            publish_guard.LOG = old_log


if __name__ == "__main__":
    unittest.main()
