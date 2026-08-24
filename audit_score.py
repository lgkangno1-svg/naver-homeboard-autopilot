# -*- coding: utf-8 -*-
"""발행 글 전체 스크린샷 + LLM 비평 채점"""
import json, re, sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
import llm

posts = json.load(open("quality_audit.json", encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 768, "height": 1200}, locale="ko-KR")
    for idx in [0, 3]:  # 최신 글 + 장보기 글
        post = posts[idx]
        m = re.search(r"/issuemans/(\d+)", post["url"])
        url = f"https://blog.naver.com/PostView.naver?blogId=issuemans&logNo={m.group(1)}"
        pg.goto(url, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(3000)
        for f in pg.frames:
            try:
                if f.evaluate("() => !!document.querySelector('.se-main-container')"):
                    f.evaluate("""async () => {
                        const main = document.querySelector('.se-main-container');
                        for (let y = 0; y < main.scrollHeight; y += 500) {
                            window.scrollTo(0, y);
                            await new Promise(r => setTimeout(r, 200));
                        }
                        window.scrollTo(0, 0);
                    }""")
                    pg.wait_for_timeout(1500)
                    break
            except Exception:
                continue
        pg.screenshot(path=f"audit_post_{idx}.png", full_page=True)
        print(f"스크린샷: audit_post_{idx}.png ({post['title'][:25]})")
    b.close()

# LLM 비평 (본문 있는 최신 2개)
for idx in [0, 3]:
    post = posts[idx]
    if not post.get("body"):
        continue
    try:
        res = llm.chat_json([
            {"role": "system", "content":
                "너는 네이버 홈판 상위노출 전문 편집자다. 실제 발행된 글을 혹평한다."},
            {"role": "user", "content":
                f"[제목] {post['title']}\n\n[본문]\n{post['body'][:2500]}\n\n"
                'JSON만: {"scores": {"hook": 0-10, "specificity": 0-10, "naturalness": 0-10, "structure": 0-10}, '
                '"verdict": "한 줄 총평"}'},
        ], max_tokens=1500, temperature=0.3)
        post["llm_scores"] = res.get("scores")
        post["verdict"] = res.get("verdict")
        print(f"\n[{post['title'][:25]}] {json.dumps(res.get('scores'), ensure_ascii=False)}")
        print("총평:", res.get("verdict"))
    except Exception as e:
        print("비평 실패:", str(e)[:100])

json.dump(posts, open("quality_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n-> quality_audit.json 갱신 완료")
