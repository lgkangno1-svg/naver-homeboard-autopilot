# -*- coding: utf-8 -*-
"""사진 삽입 모달 구조 디버깅: 사진 클릭 → 대기 → 스크린샷 + 입력요소 덤프"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
import naver

pw, browser, ctx, page = naver.launch(headless=False)
try:
    page.goto("https://blog.naver.com/issuemans/postwrite", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(9000)
    naver._dismiss_recovery(page)

    # 사진 버튼 클릭
    clicked = False
    for sel in [".se-image-toolbar-button", ".se-toolbar-item-image button", "[title='사진']", "button:has-text('사진')"]:
        try:
            btn = page.locator(sel).first
            if btn.count():
                print(f"사진 버튼 발견: {sel}")
                btn.click(timeout=5000)
                clicked = True
                break
        except Exception as e:
            print(f"  {sel} 실패: {str(e)[:60]}")
    print("클릭됨:", clicked)
    page.wait_for_timeout(4000)
    page.screenshot(path="photo_modal_1.png")

    info = page.evaluate("""() => ({
        inputs: Array.from(document.querySelectorAll('input[type=file]')).map(e => ({cls: e.className.slice(0,50), id: e.id, accept: e.accept})),
        dialogs: Array.from(document.querySelectorAll('[class*=dialog],[class*=modal],[class*=layer],[class*=popup]')).slice(0,10).map(e => ({cls: e.className.toString().slice(0,70), vis: !!(e.offsetWidth || e.offsetHeight)})),
        iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({id: f.id, src: (f.src||'').slice(0,80)}))
    })""")
    print(json.dumps(info, ensure_ascii=False, indent=1))

    # 프레임별 file input 확인
    for f in page.frames:
        try:
            c = f.locator("input[type='file']").count()
            if c:
                print("프레임에서 file input:", f.url[:80], "개수:", c)
        except Exception:
            pass
finally:
    browser.close(); pw.stop()
