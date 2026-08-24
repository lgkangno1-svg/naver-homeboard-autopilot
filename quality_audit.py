# -*- coding: utf-8 -*-
"""발행된 블로그 글을 수집해 품질/홈판 노출 관점 정량 점검"""
import json, re, sys, time

import requests

sys.stdout.reconfigure(encoding="utf-8")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

BANNED = ["알아보겠습니다", "알아보았습니다", "정리해 보았습니다", "결론적으로", "도움이 되었으면",
          "함께 알아보겠습니다", "체크해보세요", "오늘은", "끝까지", "주의하세요"]

# 1) RSS로 최근 글 목록
r = requests.get("https://rss.blog.naver.com/issuemans.xml", headers={"User-Agent": UA}, timeout=20)
rss = r.text
items = re.findall(r"<item>(.*?)</item>", rss, re.S)
print(f"RSS 최근 글: {len(items)}개\n")

posts = []
for it in items[:8]:
    title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", it, re.S)
    link = re.search(r"<link><!\[CDATA\[(.*?)\]\]></link>", it) or re.search(r"<link>(.*?)</link>", it)
    cat = re.search(r"<category><!\[CDATA\[(.*?)\]\]></category>", it, re.S)
    pub = re.search(r"<pubDate>(.*?)</pubDate>", it)
    posts.append({
        "title": title.group(1) if title else "?",
        "url": (link.group(1) if link else "?").replace("<![CDATA[", "").replace("]]>", ""),
        "category": cat.group(1) if cat else "?",
        "pubDate": pub.group(1) if pub else "?",
    })

# 2) 각 글 본문 수집 (모바일 버전)
for p in posts:
    p.setdefault("body", "")
    p.setdefault("chars", 0)
    p.setdefault("images", 0)
    p.setdefault("centered", 0)
    p.setdefault("tags", [])
    p.setdefault("sent_count", 0)
    p.setdefault("avg_sent_len", 0)
    p.setdefault("banned_found", [])
    p.setdefault("digits", 0)
    m = re.search(r"logNo=(\d+)", p["url"]) or re.search(r"/issuemans/(\d+)", p["url"])
    if not m:
        p["error"] = "logNo 없음: " + p["url"][:60]
        continue
    logno = m.group(1)
    mu = f"https://blog.naver.com/PostView.naver?blogId=issuemans&logNo={logno}"
    try:
        r2 = requests.get(mu, headers={"User-Agent": UA}, timeout=20)
        html = r2.text
        # 본문 텍스트 추출 (se-main-container 내부)
        body_m = re.search(r'class="se-main-container"(.*?)</article>', html, re.S)
        seg = body_m.group(1) if body_m else html
        text = re.sub(r"<script.*?</script>|<style.*?</style>", "", seg, flags=re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        p["body"] = text
        p["chars"] = len(text.replace("\n", ""))
        p["images"] = len(re.findall(r"postfiles\.pstatic\.net|blogfiles\.naver\.net", html))
        p["centered"] = len(re.findall(r"text-align:\s*center", html))
        p["tags"] = re.findall(r"#([\w가-힣]+)", html)[:8]
        sentences = [s for s in re.split(r"[.!?~]\s*", text) if s.strip()]
        p["sent_count"] = len(sentences)
        p["avg_sent_len"] = round(sum(len(s) for s in sentences) / max(1, len(sentences)), 1)
        p["banned_found"] = [b for b in BANNED if b in text]
        p["digits"] = len(re.findall(r"\d", text))
    except Exception as e:
        p["error"] = str(e)[:100]
    time.sleep(1)

# 3) 결과 출력
for p in posts:
    print("=" * 70)
    print(f"제목: {p['title']} ({len(p['title'])}자)")
    print(f"카테고리: {p['category']} | 발행: {p['pubDate']}")
    if p.get("error"):
        print("수집 실패:", p["error"])
        continue
    q = "“" if "“" in p["title"] else ("\"" if "\"" in p["title"] else "없음")
    d = re.search(r"\d", p["title"])
    print(f"제목 따옴표: {q} | 숫자: {'있음(pos {:.0%})'.format(d.start()/len(p['title'])) if d else '없음'} | 의문형: {'예' if p['title'].rstrip().endswith('?') else '아니오'}")
    print(f"본문: {p['chars']}자 | 문장 {p['sent_count']}개 (평균 {p['avg_sent_len']}자) | 숫자 {p['digits']}개")
    print(f"이미지: {p['images']}장 | 가운데정렬 스타일 {p['centered']}건 | 태그: {p['tags']}")
    print(f"AI스러운 금지 표현: {p['banned_found'] or '없음 ✓'}")
    print("본문 앞 200자:", p.get("body", "")[:200].replace("\n", " / "))

json.dump(posts, open("quality_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n-> quality_audit.json 저장")
