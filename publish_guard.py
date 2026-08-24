# -*- coding: utf-8 -*-
"""Idempotency and conservative post-publish verification."""
import hashlib
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "published.jsonl")
KST = ZoneInfo("Asia/Seoul")


def content_id(post):
    parts = [post.get("title", "")]
    parts.extend(post.get("intro", []))
    for sec in post.get("sections", []):
        parts.append(sec.get("heading", ""))
        parts.extend(sec.get("paragraphs", []))
    raw = "\n".join(parts).encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()[:20]


def iter_log():
    if not os.path.exists(LOG):
        return
    try:
        for line in open(LOG, encoding="utf-8"):
            try:
                yield json.loads(line)
            except Exception:
                continue
    except Exception:
        return


def already_published(cid):
    for rec in iter_log() or []:
        if rec.get("content_id") == cid and rec.get("mode") == "publish" and rec.get("status") in ("published", "verified"):
            return True
    return False


def today_slot_count(mode="publish"):
    """Count consumed schedule slots for the requested mode.

    Publish mode counts published/verified/uncertain outcomes to avoid duplicate reposting.
    Draft mode counts successful drafts so cron preview mode does not create endless drafts.
    """
    today = datetime.now(KST).strftime("%Y-%m-%d")
    valid = ("published", "verified", "uncertain") if mode == "publish" else ("draft",)
    seen = set()
    for rec in iter_log() or []:
        if not rec.get("ts", "").startswith(today) or rec.get("mode") != mode:
            continue
        if rec.get("status") not in valid:
            continue
        seen.add(rec.get("slot_id") or rec.get("content_id") or rec.get("ts"))
    return len(seen)


def verify_title(blog_id, title):
    """Best-effort verification. False means 'not confirmed', not definitely unpublished."""
    if not title:
        return False, None
    import naver
    pw = browser = None
    try:
        pw, browser, ctx, page = naver.launch(headless=True)
        urls = [
            f"https://blog.naver.com/{blog_id}",
            f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&from=postList",
        ]
        needle = re.sub(r"\s+", "", title)[:26]
        for url in urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3500)
                for frame in page.frames:
                    try:
                        txt = re.sub(r"\s+", "", frame.locator("body").inner_text(timeout=4000))
                        if needle and needle in txt:
                            return True, page.url
                    except Exception:
                        continue
            except Exception:
                continue
        return False, None
    except Exception as e:
        print("  발행 후 검증 실패(불확실로 처리):", str(e)[:100])
        return False, None
    finally:
        try:
            if browser:
                browser.close()
            if pw:
                pw.stop()
        except Exception:
            pass
