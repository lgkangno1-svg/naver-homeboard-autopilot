# -*- coding: utf-8 -*-
"""발행 글 스크린샷 + 정확한 이미지 카운트"""
import json, re, sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
posts = json.load(open("quality_audit.json", encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 430, "height": 932}, locale="ko-KR")  # 모바일 홈판과 유사한 폭
    # 첫 새 글 1개만 스크린샷
    post = posts[0]
    m = re.search(r"/issuemans/(\d+)", post["url"])
    url = f"https://blog.naver.com/PostView.naver?blogId=issuemans&logNo={m.group(1)}"
    pg.goto(url, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(3000)
    for f in pg.frames:
        try:
            if f.evaluate("() => !!document.querySelector('.se-main-container')"):
                # 스크롤하며 이미지 로드
                cnt = f.evaluate("""async () => {
                    const main = document.querySelector('.se-main-container');
                    for (let y = 0; y < main.scrollHeight; y += 600) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 300));
                    }
                    return main.querySelectorAll('img[src*="pstatic.net"]').length;
                }""")
                post["images"] = cnt
                print("이미지(스크롤 로드 후):", cnt)
                break
        except Exception:
            continue
    pg.screenshot(path="published_post_mobile.png", full_page=False)
    # 위로 스크롤 복귀 후 상단 캡처
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(500)
    pg.screenshot(path="published_post_top.png")
    b.close()

json.dump(posts, open("quality_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("저장: published_post_top.png")
