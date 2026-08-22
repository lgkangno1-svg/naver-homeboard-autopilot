# -*- coding: utf-8 -*-
"""임시저장된 글 확인용 스크린샷"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=True)
try:
    page.goto("https://blog.naver.com/issuemans/postwrite", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(8000)
    # 임시저장 목록 열기 (에디터 상단 메뉴 or 관리 페이지)
    page.goto("https://blog.naver.com/issuemans/manage/posts?filterType=temp", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(6000)
    page.screenshot(path="draft_list.png")
    print("URL:", page.url)
finally:
    browser.close(); pw.stop()
