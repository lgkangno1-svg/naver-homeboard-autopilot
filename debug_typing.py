# -*- coding: utf-8 -*-
"""에디터 입력 흐름 검증: 제목 클릭→타이핑, 본문 클릭→타이핑, 각 단계 스크린샷"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=False)
try:
    page.goto("https://blog.naver.com/issuemans/postwrite", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(10000)

    # 도움말 패널 닫기 (있으면)
    try:
        close = page.locator("button[aria-label='도움말 닫기'], .se-help-close, [class*='help'] >> role=button[name='닫기']").first
        if close.count():
            close.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # 1) 제목 영역 클릭 + 타이핑
    title_el = page.locator(".se-title-text").first
    print("title 요소 수:", page.locator(".se-title-text").count())
    title_el.click()
    page.wait_for_timeout(800)
    page.keyboard.type("자동화 테스트 제목입니다")
    page.wait_for_timeout(1500)
    page.screenshot(path="step1_title.png")

    # 2) 본문 영역 클릭 (제목 아래 빈 곳) + 타이핑
    body_area = page.locator(".se-body").first
    box = body_area.bounding_box()
    print("body box:", box)
    if box:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 200)
    page.wait_for_timeout(800)
    page.keyboard.type("본문 첫 문장 입력 테스트. 짧게 끊어 쓰는 스타일로.")
    page.keyboard.press("Enter")
    page.keyboard.type("두 번째 문장도 잘 들어가는지 확인 중입니다.")
    page.wait_for_timeout(1500)
    page.screenshot(path="step2_body.png")
    print("완료 — step1_title.png / step2_body.png 확인")
finally:
    # 저장하지 않고 종료
    browser.close()
    pw.stop()
