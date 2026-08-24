# -*- coding: utf-8 -*-
"""Execution manager for generation, image collection and conservative publishing."""
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

import images as imgmod
import naver
import publish_guard
import writer_v2 as writer

CFG = json.load(open("config.json", encoding="utf-8"))
LOGDIR = os.path.join(BASE, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOCK = os.path.join(LOGDIR, "cron.lock")


def _publish_times():
    times = sorted(dict.fromkeys(CFG.get("publish_times", [])))
    limit = max(0, int(CFG.get("posts_per_day", len(times) or 1)))
    return times[:limit]


def log_result(rec):
    rec.setdefault("ts", datetime.now(KST).isoformat(timespec="seconds"))
    with open(os.path.join(LOGDIR, "published.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _generate_unique(mode):
    last = None
    for _ in range(3):
        post = writer.generate_post()
        cid = publish_guard.content_id(post)
        last = (post, cid)
        if mode != "publish" or not publish_guard.already_published(cid):
            return post, cid
        print("  이미 성공 발행한 동일 원고 감지 → 새 소재 재생성")
    raise RuntimeError(f"중복 원고가 반복 생성됨: {last[1] if last else 'unknown'}")


def make_and_publish(mode=None, slot_id=None):
    """Create one post and handle uncertain publish outcomes without blind reposting."""
    mode = mode or ("publish" if CFG.get("publish") else "draft")
    print(f"[{datetime.now(KST):%H:%M:%S}] 글 생성 시작... mode={mode}")

    # Generation/image failures are safe to retry because no publish action has started yet.
    post, cid = _generate_unique(mode)
    print("제목:", post["title"])
    print("본문:", post.get("_chars"), "자 / 이미지 계획:", len(post.get("image_queries", [])), "장")
    quality = post.get("_quality", {})
    if quality:
        print("품질:", quality.get("editor_scores", {}), "/ 근거 스니펫", quality.get("evidence_lines", 0), "줄")

    n_img = min(len(post.get("image_queries", [])), CFG["format"]["image_max"])
    print("이미지 수집 중...")
    imgs = imgmod.fetch_images(post.get("image_queries", []), n_img)
    print(f"이미지 {len(imgs)}장 확보")

    base_rec = {
        "title": post["title"],
        "mode": mode,
        "slot_id": slot_id,
        "content_id": cid,
        "chars": post.get("_chars"),
        "images": len(imgs),
        "angle": post.get("_angle", {}).get("angle"),
        "quality": quality.get("editor_scores", {}),
    }

    # From here on, never blindly retry on an ambiguous outcome: the final click may have succeeded.
    try:
        res = naver.write_post(post, imgs, mode=mode)
    except Exception as e:
        if mode == "draft":
            log_result({**base_rec, "status": "failed", "ok": False, "error": str(e)[:300]})
            raise
        verified, url = publish_guard.verify_title(CFG["blog_id"], post["title"])
        status = "verified" if verified else "uncertain"
        log_result({**base_rec, "status": status, "ok": bool(verified), "url": url, "error": str(e)[:300]})
        print("발행 중 예외 발생 →", "게시 확인됨" if verified else "결과 불확실(중복 방지를 위해 자동 재발행 안 함)")
        return {"ok": bool(verified), "status": status, "url": url}

    if mode == "draft":
        ok = bool(res.get("ok"))
        status = "draft" if ok else "failed"
        log_result({**base_rec, "status": status, "ok": ok, "url": res.get("url")})
        return {**res, "status": status}

    if res.get("ok"):
        log_result({**base_rec, "status": "published", "ok": True, "url": res.get("url")})
        return {**res, "status": "published"}

    print("기본 발행 검증 실패 → 독립 검증 1회 수행")
    verified, url = publish_guard.verify_title(CFG["blog_id"], post["title"])
    status = "verified" if verified else "uncertain"
    log_result({**base_rec, "status": status, "ok": bool(verified), "url": url or res.get("url")})
    if verified:
        print("독립 검증에서 발행 확인:", url or CFG["blog_id"])
    else:
        print("발행 결과 불확실 — 해당 슬롯은 소진하고 자동 재발행하지 않습니다")
    return {"ok": bool(verified), "status": status, "url": url or res.get("url")}


def daily():
    times = _publish_times()
    now = datetime.now(KST)
    today = now.date()
    slots = []
    for t in times:
        h, m = map(int, t.split(":"))
        dt = datetime.combine(today, datetime.min.time(), tzinfo=KST).replace(hour=h, minute=m)
        if dt > now - timedelta(minutes=10):
            slots.append(dt)
    print(f"[KST {now:%H:%M}] 오늘 남은 슬롯 {len(slots)}개:", [s.strftime('%H:%M') for s in slots])

    for s in slots:
        wait = max(0, (s - datetime.now(KST)).total_seconds())
        jitter = random.uniform(0, min(25 * 60, int(CFG.get("schedule_jitter_minutes", 18)) * 60))
        target = wait + jitter
        if target > 0:
            print(f"{s:%H:%M} 슬롯 (+{jitter/60:.0f}분 지터)")
            time.sleep(target)
        slot_id = s.strftime("%Y-%m-%dT%H:%M")
        try:
            make_and_publish(slot_id=slot_id)
        except Exception as e:
            # Only pre-publish failures reach here; one retry is safe.
            print("발행 전 단계 실패 → 1회 재시도:", str(e)[:200])
            time.sleep(60)
            try:
                make_and_publish(slot_id=slot_id)
            except Exception as e2:
                print("재시도 실패:", str(e2)[:250])
        time.sleep(30)


def _today_slot_count():
    return publish_guard.today_slot_count()


def cron():
    """Process at most one due slot. Drafts never count as published slots."""
    if os.path.exists(LOCK):
        age = time.time() - os.path.getmtime(LOCK)
        if age < 3600:
            print("다른 cron 작업 진행 중 — 종료")
            return
        os.remove(LOCK)
    with open(LOCK, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        times = _publish_times()
        now = datetime.now(KST)
        done = _today_slot_count()
        due = []
        for t in times:
            h, m = map(int, t.split(":"))
            if now.hour > h or (now.hour == h and now.minute >= m):
                due.append(t)
        need = max(0, len(due) - done)
        print(f"[KST {now:%H:%M}] 마감 슬롯 {len(due)} / 처리 슬롯 {done} → 남은 {need}편")
        if need <= 0:
            return
        slot_id = f"{now:%Y-%m-%d}T{due[min(done, len(due)-1)]}"
        make_and_publish(mode=None if CFG.get("publish") else "draft", slot_id=slot_id)
    finally:
        try:
            os.remove(LOCK)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "login":
        naver.login(headed=True)
    elif cmd == "check":
        pw, browser, ctx, page = naver.launch(headless=True)
        try:
            print("로그인 상태:", naver.is_logged_in(page))
        finally:
            browser.close(); pw.stop()
    elif cmd == "once":
        draft = "--draft" in sys.argv
        make_and_publish(mode="draft" if draft else None, slot_id="manual")
    elif cmd == "daily":
        daily()
    elif cmd == "cron":
        cron()
    else:
        print(__doc__)
