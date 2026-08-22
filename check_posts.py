# -*- coding: utf-8 -*-
"""발행된 글 목록 확인"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=True)
try:
    page.goto("https://blog.naver.com/issuemans", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(6000)
    # iframe 구조로 본문 목록 접근
    titles = []
    for f in page.frames:
        try:
            ts = f.evaluate("""() => Array.from(document.querySelectorAll('.title, .post-title, h2, h3'))
                .map(e => e.textContent.trim()).filter(t => t && t.length > 8).slice(0, 10)""")
            titles += ts
        except Exception:
            pass
    print("발견된 제목들:")
    for t in titles[:15]:
        print(" -", t[:70])
    page.screenshot(path="blog_main.png")
finally:
    browser.close(); pw.stop()
