# -*- coding: utf-8 -*-
"""실행 관리자.
python run.py login        : 보이는 창으로 로그인 + 세션 저장
python run.py check        : 세션 유효 확인
python run.py once         : 글 1편 생성→이미지→발행 (config.publish=false면 임시저장)
python run.py once --draft : 이번 1편만 임시저장
python run.py daily        : 오늘 남은 발행 시각에 맞춰 자동 운영 (3~5편)
"""
import json, os, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

import naver
import writer
import images as imgmod

CFG = json.load(open("config.json", encoding="utf-8"))
LOGDIR = os.path.join(BASE, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOCK = os.path.join(LOGDIR, "cron.lock")


def log_result(rec):
    with open(os.path.join(LOGDIR, "published.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_and_publish(mode=None):
    mode = mode or ("publish" if CFG.get("publish") else "draft")
    print(f"[{datetime.now():%H:%M:%S}] 글 생성 시작...")
    post = writer.generate_post()
    print("제목:", post["title"])
    print("본문:", post["_chars"], "자 / 이미지 계획:", len(post["image_queries"]), "장")
    n_img = min(len(post["image_queries"]), CFG["format"]["image_max"])
    print("이미지 수집 중...")
    imgs = imgmod.fetch_images(post["image_queries"], n_img)
    print(f"이미지 {len(imgs)}장 확보")
    res = naver.write_post(post, imgs, mode=mode)
    log_result({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "title": post["title"], "mode": mode,
        "ok": res.get("ok"), "url": res.get("url"),
        "chars": post["_chars"], "images": len(imgs),
        "angle": post.get("_angle", {}).get("angle"),
    })
    return res


def daily():
    times = sorted(CFG.get("publish_times", ["09:10", "12:30", "18:40", "21:20"]))
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
        wait = (s - datetime.now(KST)).total_seconds()
        jitter = __import__("random").uniform(0, 25 * 60)  # 0~25분 지터로 사람 티 내기
        target = wait + jitter
        if target > 0:
            print(f"{s:%H:%M} (+{jitter/60:.0f}분 지터)까지 {target/60:.0f}분 대기")
            time.sleep(target)
        for attempt in range(2):
            try:
                make_and_publish()
                break
            except Exception as e:
                print("실패, 재시도:", str(e)[:200])
                time.sleep(300)
        time.sleep(60)


def _today_published_count():
    """오늘(KST) 발행/임시저장 완료 수"""
    n = 0
    p = os.path.join(LOGDIR, "published.jsonl")
    if not os.path.exists(p):
        return 0
    today = datetime.now(KST).strftime("%Y-%m-%d")
    for line in open(p, encoding="utf-8"):
        try:
            rec = json.loads(line)
            if rec.get("ts", "").startswith(today) and rec.get("ok"):
                n += 1
        except Exception:
            pass
    return n


def cron():
    """cron용: 지금 시각(KST) 기준 마감된 슬롯 중 미완료 것을 1개 처리. 중복 실행 잠금 포함."""
    if os.path.exists(LOCK):
        age = time.time() - os.path.getmtime(LOCK)
        if age < 3600:  # 1시간 내 잠금 = 다른 실행 중
            print("다른 cron 작업 진행 중 — 종료")
            return
        os.remove(LOCK)
    open(LOCK, "w").write(str(os.getpid()))
    try:
        times = sorted(CFG.get("publish_times", []))
        now = datetime.now(KST)
        done = _today_published_count()
        due_idx = sum(1 for t in times
                      if (lambda h, m: now.hour > h or (now.hour == h and now.minute >= m))
                      (*map(int, t.split(":"))))
        need = max(0, due_idx - done)
        print(f"[KST {now:%H:%M}] 마감 슬롯 {due_idx} / 완료 {done} → 처리할 {need}편")
        if need <= 0:
            return
        mode = None if CFG.get("publish") else "draft"
        try:
            make_and_publish(mode=mode)
        except Exception as e:
            print("발행 실패:", str(e)[:300])
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "login":
        naver.login(headed=True)
    elif cmd == "check":
        pw, browser, ctx, page = naver.launch(headless=True)
        print("로그인 상태:", naver.is_logged_in(page))
        browser.close(); pw.stop()
    elif cmd == "once":
        draft = "--draft" in sys.argv
        make_and_publish(mode="draft" if draft else None)
    elif cmd == "daily":
        daily()
    elif cmd == "cron":
        cron()
    else:
        print(__doc__)
