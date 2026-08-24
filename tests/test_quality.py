import json
import os
import tempfile
import unittest

import publish_guard
import research
import writer_v2


class QualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", encoding="utf-8") as f:
            cls.cfg = json.load(f)

    def _post(self, intro, title="통신비 절약 전에 먼저 확인할 조건은?"):
        para = "생활비를 줄일 때는 가격 하나보다 조건과 사용 빈도를 같이 보는 편이 좋습니다. " * 8
        return {
            "title": title,
            "intro": [intro, para],
            "sections": [
                {"heading": "약정 조건부터 확인합니다", "paragraphs": [para], "emphasis": "조건을 먼저 비교합니다.", "centered_lines": []},
                {"heading": "총비용을 함께 비교합니다", "paragraphs": [para], "emphasis": "총비용을 확인합니다.", "centered_lines": []},
                {"heading": "해지 조건도 놓치지 않습니다", "paragraphs": [para], "emphasis": "해지 조건도 확인합니다.", "centered_lines": []}
            ],
            "conclusion": [para],
            "image_queries": ["휴대폰 요금 명세서", "통신비 비교"]
        }

    def _bundle(self, text="", high_stakes=False, official_count=0, tier=2):
        items = []
        if text:
            items.append({
                "title": "참고자료",
                "snippet": text,
                "url": "https://example.com/info",
                "domain": "example.com",
                "tier": tier,
                "source_type": "web",
            })
        return {"query": "테스트", "high_stakes": high_stakes, "official_count": official_count, "items": items}

    def test_fake_experience_is_rejected(self):
        post = self._post("제가 직접 3개월 사용해 보니 통신비가 줄었습니다.")
        issues = writer_v2._deterministic_issues(post, self.cfg, self._bundle(), [])
        self.assertTrue(any("체험" in issue or "사용기간" in issue for issue in issues))

    def test_plain_informational_copy_does_not_trigger_fake_experience(self):
        post = self._post("통신비 절약을 고민한다면 먼저 약정과 데이터 사용량을 확인해야 합니다.")
        issues = writer_v2._deterministic_issues(post, self.cfg, self._bundle(), [])
        self.assertFalse(any("체험" in issue or "사용기간" in issue for issue in issues))

    def test_unsupported_money_claim_is_rejected(self):
        post = self._post("이 요금제는 월 3만원을 아낄 수 있다고 단정하면 안 됩니다.")
        issues = writer_v2._deterministic_issues(post, self.cfg, self._bundle(), [])
        self.assertTrue(any("숫자 주장" in issue for issue in issues))

    def test_supported_money_claim_passes_number_guard(self):
        post = self._post("검색 자료에는 월 3만원 절감 사례가 표시되어 있습니다.")
        bundle = self._bundle("월 3만원 절감 사례가 표시되어 있습니다")
        issues = writer_v2._deterministic_issues(post, self.cfg, bundle, [])
        self.assertFalse(any("숫자 주장" in issue for issue in issues))

    def test_high_stakes_number_requires_official_source(self):
        post = self._post("지원 조건에는 30만원이라는 금액이 표시되어 있습니다.", title="정부지원금 30만원 조건은 어디서 확인할까?")
        bundle = self._bundle("지원 조건 30만원", high_stakes=True, official_count=0)
        issues = writer_v2._deterministic_issues(post, self.cfg, bundle, [])
        self.assertTrue(any("공식출처" in issue for issue in issues))

    def test_recent_title_similarity_is_rejected(self):
        title = "통신비 절약 전에 먼저 확인할 조건은?"
        post = self._post("약정부터 확인해야 합니다.", title=title)
        issues = writer_v2._deterministic_issues(post, self.cfg, self._bundle(), [title])
        self.assertTrue(any("중복" in issue for issue in issues))

    def test_content_id_is_stable(self):
        post = self._post("통신비 절약은 현재 요금제부터 확인하는 것이 시작입니다.")
        self.assertEqual(publish_guard.content_id(post), publish_guard.content_id(post))


class SourceRankingTests(unittest.TestCase):
    def test_government_domain_is_tier_one(self):
        tier, label = research.source_rank("https://www.gov.kr/portal/service/serviceInfo/test")
        self.assertEqual(tier, 1)
        self.assertEqual(label, "official")

    def test_blog_is_low_priority_ugc(self):
        tier, label = research.source_rank("https://blog.naver.com/example/123")
        self.assertEqual(tier, 5)
        self.assertEqual(label, "ugc")

    def test_high_stakes_detection(self):
        self.assertTrue(research.is_high_stakes("근로장려금 신청 자격"))
        self.assertFalse(research.is_high_stakes("주방세제 비교"))


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
