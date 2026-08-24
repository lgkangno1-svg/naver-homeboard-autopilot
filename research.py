# -*- coding: utf-8 -*-
"""Lightweight evidence collection for safer, higher-quality blog drafts."""
import re
from urllib.parse import quote


def collect_naver_evidence(query, max_lines=24):
    """Collect visible Naver search snippets. Returns evidence text, not verified facts.

    The writer is explicitly instructed to treat these as snippets and to avoid inventing
    details that are not present in the evidence.
    """
    try:
        from playwright.sync_api import sync_playwright
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=ua, viewport={"width": 1280, "height": 900})
            page.goto(
                f"https://search.naver.com/search.naver?query={quote(query)}",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            page.wait_for_timeout(2200)
            text = page.evaluate("() => document.body.innerText")
            browser.close()
    except Exception as e:
        print("  근거 수집 실패(계속 진행):", str(e)[:100])
        return ""

    banned = ("로그인", "검색", "메뉴", "더보기", "NAVER", "네이버앱")
    lines, seen = [], set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not 18 <= len(line) <= 130:
            continue
        if line in seen or any(line == x for x in banned):
            continue
        if re.fullmatch(r"[\d\s,.:/%~-]+", line):
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= max_lines:
            break
    if not lines:
        return ""
    return "\n".join(f"- {x}" for x in lines)
