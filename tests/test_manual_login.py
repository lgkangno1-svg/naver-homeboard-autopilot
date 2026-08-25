import unittest

import manual_login


class ManualLoginHelperTests(unittest.TestCase):
    def test_login_url_is_naver(self):
        self.assertIn("nid.naver.com", manual_login.LOGIN_URL)

    def test_login_detector_rejects_login_page(self):
        class Page:
            url = "https://nid.naver.com/nidlogin.login"
        self.assertFalse(manual_login._looks_logged_in(Page()))

    def test_login_detector_accepts_naver_home(self):
        class Page:
            url = "https://www.naver.com/"
        self.assertTrue(manual_login._looks_logged_in(Page()))


if __name__ == "__main__":
    unittest.main()
