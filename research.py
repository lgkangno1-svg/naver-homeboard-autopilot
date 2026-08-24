# -*- coding: utf-8 -*-
"""Source-ranked evidence collection for safer, higher-quality blog drafts."""
import re
from urllib.parse import quote, urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

HIGH_STAKES_HINTS = (
    "정부", "지원금", "장려금", "세금", "환급", "보조금", "신청", "자격", "정책",
    "법", "금리", "보험", "통신요금", "요금제", "공공", "복지", "근로장려금",
)
OFFICIAL_HOST_HINTS = (
    "gov.kr", "korea.kr", "law.go.kr", "easylaw.go.kr", "nts.go.kr", "mois.go.kr",
    "mohw.go.kr", "moel.go.kr", "msit.go.kr", "kca.go.kr", "fss.or.kr", "bok.or.kr",
)
UGC_HOST_HINTS = (
    "blog.naver.com", "cafe.naver.com", "tistory.com", "brunch.co.kr", "youtube.com",
    "instagram.com", "facebook.com", "threads.net",
)
COMMERCE_HOST_HINTS = (
    "shopping.naver.com", "smartstore.naver.com", "coupang.com", "11st.co.kr", "gmarket.co.kr",
    "auction.co.kr", "ssg.com", "lotteon.com",
)
NEWS_HOST_HINTS = ("news.naver.com", "newsis.com", "yna.co.kr", "mk.co.kr", "hankyung.com")


def is_high_stakes(query):
    q = (query or "").lower()
    return any(h.lower() in q for h in HIGH_STAKES_HINTS)


def _host(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def source_rank(url):
    """Return (tier, label). Lower tier is stronger evidence."""
    host = _host(url)
    if not host:
        return 9, "unknown"
    if host.endswith(".go.kr") or host.endswith(".mil.kr") or any(x in host for x in OFFICIAL_HOST_HINTS):
        return 1, "official"
    if any(x in host for x in UGC_HOST_HINTS):
        return 5, "ugc"
    if any(x in host for x in COMMERCE_HOST_HINTS):
        return 4, "commerce"
    if any(x in host for x in NEWS_HOST_HINTS) or "news." in host:
        return 3, "news"
    if host.endswith(".ac.kr") or host.endswith(".or.kr"):
        return 2, "institution"
    return 2, "web"


def _clean_text(text, limit=260):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def _search_once(query, max_items=24):
    """Collect visible search result anchors and nearby text from Naver search."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, viewport={"width": 1280, "height": 1000})
            page.goto(
                f"https://search.naver.com/search.naver?query={quote(query)}",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            page.wait_for_timeout(2200)
            raw = page.evaluate("""() => {
                const out = [];
                for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                    const href = a.href || '';
                    const title = (a.innerText || a.textContent || '').trim();
                    if (!href.startsWith('http') || title.length < 4) continue;
                    let node = a;
                    for (let i=0; i<3 && node?.parentElement; i++) node = node.parentElement;
                    const snippet = (node?.innerText || title).trim();
                    out.push({href, title, snippet});
                }
                return out.slice(0, 250);
            }""")
            browser.close()
    except Exception as e:
        print("  검색 근거 수집 실패:", str(e)[:100])
        return []

    out, seen = [], set()
    for item in raw:
        url = item.get("href", "")
        host = _host(url)
        if not host:
            continue
        # Naver utility/search navigation is not evidence. Naver blog/news/shopping are handled explicitly.
        if host in ("search.naver.com", "m.search.naver.com", "www.naver.com"):
            continue
        title = _clean_text(item.get("title"), 130)
        snippet = _clean_text(item.get("snippet"), 320)
        if not title or len(snippet) < 12:
            continue
        key = (host, title[:80])
        if key in seen:
            continue
        seen.add(key)
        tier, label = source_rank(url)
        out.append({
            "title": title,
            "snippet": snippet,
            "url": url,
            "domain": host,
            "tier": tier,
            "source_type": label,
        })
    out.sort(key=lambda x: (x["tier"], -len(x["snippet"])))
    return out[:max_items]


def collect_evidence(query, max_items=12, official_search=True):
    """Return a structured evidence bundle with source strength metadata."""
    high_stakes = is_high_stakes(query)
    items = _search_once(query, max_items=max_items * 2)
    if high_stakes and official_search:
        # A second official-domain-biased query improves policy/support/eligibility reliability.
        items += _search_once(f"{query} site:go.kr", max_items=max_items)

    dedup, seen = [], set()
    for item in sorted(items, key=lambda x: (x["tier"], -len(x["snippet"]))):
        key = (item["domain"], item["title"][:80])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= max_items:
            break

    official_count = sum(1 for x in dedup if x["tier"] == 1)
    return {
        "query": query,
        "high_stakes": high_stakes,
        "official_count": official_count,
        "items": dedup,
    }


def format_evidence(bundle, max_chars=5000):
    items = (bundle or {}).get("items", [])
    if not items:
        return "- 검색 근거 없음"
    lines = []
    for item in items:
        lines.append(
            f"- [T{item['tier']} {item['source_type']} | {item['domain']}] "
            f"{item['title']} — {item['snippet']}"
        )
    text = "\n".join(lines)
    return text[:max_chars]


def evidence_text(bundle):
    return "\n".join(
        f"{x.get('title','')} {x.get('snippet','')}" for x in (bundle or {}).get("items", [])
    )


def evidence_sources(bundle, limit=8):
    return [
        {
            "domain": x.get("domain"),
            "tier": x.get("tier"),
            "source_type": x.get("source_type"),
            "title": x.get("title"),
            "url": x.get("url"),
        }
        for x in (bundle or {}).get("items", [])[:limit]
    ]


def collect_naver_evidence(query, max_lines=24):
    """Backward-compatible text API used by older scripts."""
    bundle = collect_evidence(query, max_items=max(6, min(max_lines, 16)))
    return format_evidence(bundle)
