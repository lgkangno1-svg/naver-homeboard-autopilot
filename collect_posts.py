# -*- coding: utf-8 -*-
"""발행 글 본문을 Playwright로 렌더링 수집 -> quality_audit.json 갱신"""
import json, re, sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

posts = json.load(open("quality_audit.json", encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 900}, locale="ko-KR")
    for post in posts:
        m = re.search(r"/issuemans/(\d+)", post["url"]) or re.search(r"logNo=(\d+)", post["url"])
        if not m:
            continue
        url = f"https://blog.naver.com/PostView.naver?blogId=issuemans&logNo={m.group(1)}"
        try:
            pg.goto(url, wait_until="networkidle", timeout=30000)
            pg.wait_for_timeout(4000)
            data = None
            for f in pg.frames:  # 본문은 PostView iframe 안에 있음
                try:
                    has = f.evaluate("() => !!document.querySelector('.se-main-container')")
                    if not has:
                        continue
                    data = f.evaluate("""() => {
                        const main = document.querySelector('.se-main-container');
                        const text = main.innerText || '';
                        const imgs = Array.from(main.querySelectorAll('img')).filter(i => (i.src||'').includes('pstatic.net') && i.naturalWidth > 200).length;
                        const centered = Array.from(main.querySelectorAll('[style*="text-align"]')).filter(e => e.style.textAlign === 'center' && e.innerText.trim().length > 10).length;
                        const centerCls = main.querySelectorAll('.se-align-center, [class*="align-center"]').length;
                        const tags = Array.from(document.querySelectorAll('.post_tag a, [class*="tag"] a')).map(e => e.textContent.trim()).filter(t => t && t.length > 1).slice(0, 10);
                        return {text, imgs, centered: centered + centerCls, tags};
                    }""")
                    break
                except Exception:
                    continue
            if data is None:
                post["error"] = "본문 프레임 미발견"
                continue
            post["body"] = data["text"]
            post["chars"] = len(data["text"].replace("\n", "").replace(" ", ""))
            post["images"] = data["imgs"]
            post["centered"] = data["centered"]
            post["tags"] = data["tags"]
            body = data["text"]
            sentences = [s for s in re.split(r"[.!?~]\s*", body) if s.strip()]
            post["sent_count"] = len(sentences)
            post["avg_sent_len"] = round(sum(len(s.strip()) for s in sentences) / max(1, len(sentences)), 1)
            post["digits"] = len(re.findall(r"\d", body))
            BANNED = ["알아보겠습니다", "알아보았습니다", "정리해 보았습니다", "결론적으로", "도움이 되었으면",
                      "함께 알아보겠습니다", "체크해보세요", "끝까지", "주의하세요"]
            post["banned_found"] = [x for x in BANNED if x in body]
            post["paragraphs"] = len([x for x in body.split("\n") if x.strip()])
        except Exception as e:
            post["error"] = str(e)[:120]
        print("수집:", post["title"][:25], "|", post.get("chars", "?"), "자 |", post.get("error", ""))
    b.close()

json.dump(posts, open("quality_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for p in posts:
    print(f"{p['title'][:30]} | {p.get('chars','?')}자 | 이미지 {p.get('images','?')} | 문단 {p.get('paragraphs','?')} | "
          f"평균문장 {p.get('avg_sent_len','?')}자 | 가운데 {p.get('centered','?')} | 태그 {len(p.get('tags',[]))}개 | 금지어 {p.get('banned_found', [])}")
