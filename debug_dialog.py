# -*- coding: utf-8 -*-
"""복구 다이얼로그 정복: DOM 덤프 + 다양한 클릭 시도"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=False)
try:
    page.goto("https://blog.naver.com/issuemans/postwrite", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(9000)

    # 다이얼로그 HTML 덤프
    html = page.evaluate("""() => {
        const p = document.querySelector('.se-popup');
        return p ? p.outerHTML.slice(0, 2500) : 'no-popup';
    }""")
    print("=== se-popup HTML ===")
    print(html)

    # 버튼 목록
    btns = page.evaluate("""() => Array.from(document.querySelectorAll('.se-popup button, .se-popup [role=button]')).map(e => ({
        tag: e.tagName, cls: e.className.toString().slice(0,60), txt: e.textContent.trim().slice(0,15)
    }))""")
    print("=== 다이얼로그 버튼 ===")
    print(json.dumps(btns, ensure_ascii=False, indent=1))

    # 취소 버튼 좌표 클릭
    box = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('.se-popup button'));
        const c = btns.find(b => b.textContent.includes('취소'));
        if (!c) return null;
        const r = c.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")
    print("취소 버튼 좌표:", box)
    if box:
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(2000)
        still = page.evaluate("() => !!document.querySelector('.se-popup')")
        print("클릭 후 팝업 존재:", still)
        page.screenshot(path="after_cancel.png")
finally:
    browser.close(); pw.stop()
