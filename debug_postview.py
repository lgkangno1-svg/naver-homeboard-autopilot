# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(locale="ko-KR")
    pg.goto("https://blog.naver.com/issuemans/224381468533", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(4000)
    print("URL:", pg.url)
    print("frames:", [f.url[:80] for f in pg.frames])
    for f in pg.frames:
        try:
            t = f.evaluate("() => (document.querySelector('.se-main-container')||{}).innerText ? document.querySelector('.se-main-container').innerText.length : 0")
            if t:
                print("본문 프레임:", f.url[:80], "길이:", t)
        except Exception:
            pass
    pg.screenshot(path="postview_debug.png")
    b.close()
