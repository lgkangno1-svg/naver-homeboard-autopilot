# -*- coding: utf-8 -*-
"""미니PC chromium 실행 테스트"""
from playwright.sync_api import sync_playwright

p = sync_playwright().start()
try:
    b = p.chromium.launch(headless=True)
    print("LAUNCH_OK", b.version)
    pg = b.new_page()
    pg.goto("https://www.naver.com", timeout=30000)
    print("NAVER_TITLE:", pg.title()[:40])
    b.close()
except Exception as e:
    print("LAUNCH_FAIL:", str(e)[:500])
finally:
    p.stop()
