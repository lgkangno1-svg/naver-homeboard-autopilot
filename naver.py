# -*- coding: utf-8 -*-
"""네이버 블로그 자동 발행 (사람처럼 입력).
- 눈에 보이는 Chrome(Chromium) 창 사용
- 글자 단위 랜덤 딜레이 타이핑, 마우스 이동 후 클릭 (즉시 주입 금지)
- 세션 재사용: storage_state.json
"""
import json, os, random, re, sys, time

from dotenv import load_dotenv

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "storage_state.json")
BLOG_ID = os.getenv("NAVER_BLOG_ID") or json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))["blog_id"]

sys.stdout.reconfigure(encoding="utf-8")


def _cfg():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def _sleep(a=None, b=None):
    hl = _cfg().get("human_like", {})
    a = a if a is not None else hl.get("action_delay_ms", [300, 1200])[0]
    b = b if b is not None else hl.get("action_delay_ms", [300, 1200])[1]
    time.sleep(random.uniform(a, b) / 1000)


def human_type(page, text, delay_range=None):
    """글자 단위 타이핑. 문장부호에서 살짝 더 쉼."""
    hl = _cfg().get("human_like", {})
    lo, hi = delay_range or hl.get("type_delay_ms", [45, 160])
    for ch in text:
        page.keyboard.type(ch, delay=0)
        time.sleep(random.uniform(lo, hi) / 1000)
        if ch in ".,!?~":
            time.sleep(random.uniform(0.08, 0.25))


def human_click(page, locator):
    """요소로 마우스를 이동(스텝+지터)한 뒤 클릭. 좌표 클릭 성공 시 즉시 반환."""
    try:
        box = locator.bounding_box(timeout=5000)
    except Exception:
        box = None
    if box:
        tx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
        ty = box["y"] + box["height"] * random.uniform(0.35, 0.65)
        page.mouse.move(tx, ty, steps=random.randint(8, 25))
        time.sleep(random.uniform(0.05, 0.2))
        page.mouse.down()
        time.sleep(random.uniform(0.03, 0.09))
        page.mouse.up()
        return
    locator.click()


def launch(headless=False):
    """브라우저 실행. HEADLESS=1 환경변수면 서버 모드(강제 헤드리스).
    채널: chrome 없는 환경(Linux 등)은 chromium으로 자동 폴백."""
    from playwright.sync_api import sync_playwright
    if os.getenv("HEADLESS") == "1":
        headless = True
    pw = sync_playwright().start()
    channel = os.getenv("BROWSER_CHANNEL", "chrome")
    args = ["--disable-blink-features=AutomationControlled",
            "--start-maximized" if not headless else "--window-size=1400,1000"]
    try:
        browser = pw.chromium.launch(headless=headless, channel=channel, args=args)
    except Exception:
        browser = pw.chromium.launch(headless=headless, args=args)
    kwargs = {"viewport": None if not headless else {"width": 1400, "height": 1000},
              "locale": "ko-KR", "timezone_id": "Asia/Seoul"}
    if os.path.exists(STATE):
        kwargs["storage_state"] = STATE
    ctx = browser.new_context(**kwargs)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page = ctx.new_page()
    return pw, browser, ctx, page


def is_logged_in(page):
    page.goto(f"https://blog.naver.com/{BLOG_ID}/postwrite", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(3500)
    return "nid.naver.com" not in page.url and "login" not in page.url.lower()


def login(headed=True):
    """헤드리스면 헤드리스로, 기본은 보이는 창으로 로그인 후 세션 저장."""
    pw, browser, ctx, page = launch(headless=not headed)
    try:
        page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        nid = os.getenv("NAVER_ID")
        npw = os.getenv("NAVER_PW")
        id_el = page.locator("#id")
        id_el.click()
        _sleep(200, 500)
        human_type(page, nid, (60, 140))
        _sleep(300, 800)
        pw_el = page.locator("#pw")
        pw_el.click()
        _sleep(200, 500)
        human_type(page, npw, (60, 150))
        _sleep(400, 900)
        human_click(page, page.locator("#loginBtn_row:visible, #loginBtn_column:visible, .btn_login, button[type='submit']").first)
        # 로그인 처리 대기 (성공 시 naver.com 등으로 이동)
        for _ in range(24):
            page.wait_for_timeout(2500)
            if "nid.naver.com" not in page.url:
                break
        # 캡차/본인인증 감지 → 최대 5분 대기(사람이 직접 해결)
        for i in range(60):
            if "nid.naver.com" not in page.url:
                break
            captcha = page.locator("#captcha, .captcha_img, iframe[src*='captcha'], img[alt*='캡차']").count()
            if captcha:
                print(f"[캡차 감지] 브라우저 창에서 직접 해결해 주세요... ({i*5}초)")
            page.wait_for_timeout(5000)
        if "nid.naver.com" in page.url:
            page.screenshot(path=os.path.join(BASE, "login_failed.png"))
            raise RuntimeError("로그인 실패 — login_failed.png 확인")
        ctx.storage_state(path=STATE)
        print("로그인 성공, 세션 저장:", STATE)
        return True
    finally:
        browser.close()
        pw.stop()


def _editor(page):
    """신버전 에디터: 최상위 문서에 렌더링됨"""
    return page


def _toolbar_click(page, titles, fallback_keys=None):
    """툴바 버튼 클릭 시도 (여러 셀렉터), 실패 시 키보드 폴백."""
    for t in titles:
        try:
            btn = page.locator(f"[title*='{t}'], [aria-label*='{t}'], button:has-text('{t}')").first
            if btn.count():
                human_click(page, btn)
                _sleep(200, 500)
                return True
        except Exception:
            continue
    if fallback_keys:
        for k in fallback_keys:
            page.keyboard.press(k)
            time.sleep(0.1)
    return False


def _dismiss_recovery(page):
    """'작성 중인 글이 있습니다' 복구 팝업(se-popup) → 취소. 없어질 때까지 반복."""
    dismissed = False
    for _ in range(3):
        try:
            if not page.locator(".se-popup-button-cancel").count():
                break
            print("  이전 작성본 복구 프롬프트 → 취소 처리")
            try:
                page.locator(".se-popup-button-cancel").first.click(timeout=3000)
            except Exception:
                # 좌표 클릭 폴백
                box = page.evaluate("""() => {
                    const b = document.querySelector('.se-popup-button-cancel');
                    if (!b) return null;
                    const r = b.getBoundingClientRect();
                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                }""")
                if box:
                    page.mouse.click(box["x"], box["y"])
                else:
                    page.evaluate("() => { const b = document.querySelector('.se-popup-button-cancel'); if (b) b.click(); }")
            page.wait_for_timeout(1500)
            dismissed = True
        except Exception:
            break
    return dismissed


def _find_file_input(page):
    """모든 프레임에서 input[type=file] 탐색"""
    for f in page.frames:
        try:
            loc = f.locator("input[type='file']")
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def _wait_file_input(page, timeout_s=15):
    """파일 입력이 나타날 때까지 폴링"""
    end = time.time() + timeout_s
    while time.time() < end:
        inp = _find_file_input(page)
        if inp:
            return inp
        page.wait_for_timeout(1000)
    return None


def _insert_image(page, jpg_path):
    """커서 위치에 사진 삽입: 툴바 사진 → 파일 선택 → 삽입/확인"""
    ok = False
    for sel in [".se-image-toolbar-button", ".se-toolbar-item-image button", "[title='사진']", "button:has-text('사진')"]:
        try:
            btn = page.locator(sel).first
            if btn.count():
                human_click(page, btn)
                ok = True
                break
        except Exception:
            continue
    if not ok:
        print("  [경고] 사진 버튼을 못 찾아 이 위치 이미지 생략")
        return False
    # 모달의 파일 입력 대기 (재클릭 포함)
    inp = _wait_file_input(page, 12)
    if inp is None:
        try:
            btn = page.locator(".se-image-toolbar-button, .se-toolbar-item-image button").first
            if btn.count():
                human_click(page, btn)
        except Exception:
            pass
        inp = _wait_file_input(page, 12)
    if inp is None:
        print("  [경고] 파일 입력 요소 없음 — 이 위치 이미지 생략")
        page.keyboard.press("Escape")
        return False
    try:
        inp.set_input_files(jpg_path, timeout=10000)
    except Exception as e:
        print("  [경고] 파일 입력 실패:", str(e)[:80])
        page.keyboard.press("Escape")
        return False
    page.wait_for_timeout(random.uniform(4000, 7000))
    # 삽입/확인 버튼
    clicked = False
    for name in ["삽입", "확인", "완료"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count():
                human_click(page, btn.last)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    # 커서가 이미지 뒤로 가도록 한 줄 확보
    try:
        page.keyboard.press("End")
        page.keyboard.press("Enter")
    except Exception:
        pass
    _sleep(300, 800)
    return True


def _type_paragraphs(page, paragraphs, enter_between=True):
    for i, para in enumerate(paragraphs):
        human_type(page, para)
        if enter_between and i < len(paragraphs) - 1:
            page.keyboard.press("Enter")
            time.sleep(random.uniform(0.1, 0.3))


def write_post(post, images, mode="publish"):
    """images: [(query, jpeg_bytes), ...] — post의 이미지 배치 계획에 따라 삽입.
    mode: publish | draft"""
    cfg = _cfg()
    pw, browser, ctx, page = launch(headless=False)
    tmpdir = os.path.join(BASE, "downloads")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        if not is_logged_in(page):
            print("세션 만료 — 재로그인 필요")
            browser.close(); pw.stop()
            login(headed=True)
            pw, browser, ctx, page = launch(headless=False)
            if not is_logged_in(page):
                raise RuntimeError("재로그인 후에도 진입 실패")
        page.wait_for_timeout(6000)

        # 이전 작성본 복구 프롬프트 처리
        _dismiss_recovery(page)

        # 도움말 패널 닫기 시도 (열려있으면)
        try:
            for sel in ["[aria-label='도움말 닫기']", ".se-help-close", "button:has-text('닫기')"]:
                b = page.locator(sel).first
                if b.count():
                    b.click(timeout=2000)
                    page.wait_for_timeout(800)
                    break
        except Exception:
            pass

        _sleep(500, 1200)
        blog_id = cfg["blog_id"]

        # 제목
        title_el = page.locator(".se-title-text").first
        human_click(page, title_el)
        _sleep(200, 500)
        human_type(page, post["title"])
        _sleep(400, 900)

        # 본문 진입 (제목에서 Enter → 본문 첫 줄)
        page.keyboard.press("Enter")
        time.sleep(0.4)

        img_paths = []
        for i, (q, data) in enumerate(images):
            p = os.path.join(tmpdir, f"img_{int(time.time())}_{i}.jpg")
            open(p, "wb").write(data)
            img_paths.append(p)

        qi = iter(img_paths)

        def next_img():
            try:
                return next(qi)
            except StopIteration:
                return None

        # 1) 대표 이미지 (제목 바로 아래)
        p = next_img()
        if p:
            _insert_image(page, p)

        def para_break(n=1):
            """문단 사이 여백 (빈 줄 삽입으로 가독성 확보)"""
            for _ in range(n):
                page.keyboard.press("Enter")
                time.sleep(random.uniform(0.08, 0.2))

        # 2) 인트로
        page.keyboard.press("Enter")
        _type_paragraphs(page, post.get("intro", []))
        para_break(2)

        # 3) 섹션들
        for si, sec in enumerate(post.get("sections", [])):
            # 소제목 (굵게) — "1. " 류 번호 제거: 에디터 자동 목록 변환으로 텍스트 유실 방지
            heading = re.sub(r"^\s*\d+[.．)]\s*", "", sec["heading"]).strip() or sec["heading"]
            human_type(page, heading)
            page.keyboard.press("Home")
            page.keyboard.press("Shift+End")
            page.keyboard.press("Control+b")
            page.keyboard.press("End")
            page.keyboard.press("Enter")
            time.sleep(0.15)
            # 볼드 상속 해제 시도
            page.keyboard.press("Control+b")
            time.sleep(0.1)
            _type_paragraphs(page, sec.get("paragraphs", []))
            para_break(1)
            # 강조 문장 (굵게)
            if sec.get("emphasis"):
                human_type(page, sec["emphasis"])
                page.keyboard.press("Home")
                page.keyboard.press("Shift+End")
                page.keyboard.press("Control+b")
                page.keyboard.press("End")
                para_break(1)
                time.sleep(0.15)
                page.keyboard.press("Control+b")
            # 중앙정렬 한 줄들 (섹션 중 1곳)
            if sec.get("centered_lines"):
                _toolbar_click(page, ["가운데"])
                _type_paragraphs(page, sec["centered_lines"])
                page.keyboard.press("Enter")
            # 섹션 사이 이미지
            if si < len(post.get("sections", [])) - 1:
                p = next_img()
                if p:
                    _insert_image(page, p)
                else:
                    para_break(2)

        # 4) 결말
        _type_paragraphs(page, post.get("conclusion", []))

        # 5) 유실 검증: 에디터 텍스트가 기대 길이의 60% 미만이면 발행 중단 → 임시저장
        _sleep(400, 800)
        try:
            editor_text = page.evaluate("""() => {
                const main = document.querySelector('.se-main-container, .se-body');
                return main ? main.innerText.length : 0;
            }""")
        except Exception:
            editor_text = 0
        expected = post.get("_chars", 1000)
        if editor_text < expected * 0.6:
            print(f"  [경고] 에디터 내용 {editor_text}자 < 기대 {expected}자의 60% — 유실 의심, 임시저장으로 전환")
            mode = "draft"

        # 6) 전체 가운데정렬 (읽기 편한 홈판 스타일)
        _sleep(400, 900)
        page.keyboard.press("Control+a")
        time.sleep(0.4)
        _toolbar_click(page, ["가운데 정렬", "가운데정렬", "가운데"], fallback_keys=["Control+Shift+e"])
        time.sleep(0.5)
        page.keyboard.press("Control+End")

        _sleep(800, 1600)
        result = {"mode": mode, "title": post["title"]}
        if mode == "draft":
            btn = page.locator("[class*='save_btn']").first
            human_click(page, btn)
            page.wait_for_timeout(3000)
            result["ok"] = True
            result["saved_chars"] = editor_text
            print("임시저장 완료")
        else:
            btn = page.locator("[class*='publish_btn']").first
            human_click(page, btn)
            page.wait_for_timeout(2500)
            # 발행 설정 다이얼로그: 카테고리 + 태그
            cat = cfg.get("category")
            if cat:
                try:
                    for sel_el in page.locator("select").all():
                        labels = sel_el.locator("option").all_text_contents()
                        if any(cat in l for l in labels):
                            sel_el.select_option(label=next(l for l in labels if cat in l))
                            print("  카테고리 설정:", cat)
                            break
                except Exception as e:
                    print("  카테고리 선택 생략:", str(e)[:60])
            try:
                tag_box = page.locator("textarea[placeholder*='태그'], input[placeholder*='태그']").first
                if tag_box.count():
                    human_click(page, tag_box)
                    tags = [post.get("_angle", {}).get("keyword") or "", cfg["topic"]["name"].split("·")[0]]
                    tags += [t for t in cfg["topic"]["keywords"][:2] if t]
                    for t in [x for x in tags if x][:5]:
                        human_type(page, t, (30, 80))
                        page.keyboard.press("Enter")
                        time.sleep(0.2)
            except Exception as e:
                print("  태그 입력 생략:", str(e)[:60])
            _sleep(400, 900)
            # 다이얼로그의 최종 발행 버튼 (상단 툴바 발행과 구별해 마지막 것)
            final = page.locator("button:has-text('발행')").last
            human_click(page, final)
            # 캡차/클라우드플레어 챌린지 감지 시 사람이 창에서 직접 해결하도록 대기
            for i in range(60):
                try:
                    vis = [
                        page.locator(s).first.is_visible()
                        for s in ["iframe[src*='captcha']", "iframe[id*='ncaptcha']",
                                  "iframe[src*='turnstile']", "[class*='challenge']"]
                        if page.locator(s).count()
                    ]
                except Exception:
                    vis = []
                if not any(vis):
                    break
                if i % 6 == 0:
                    print(f"[챌린지 감지] 열린 브라우저 창에서 직접 해결해 주세요... ({i*5}초 경과)")
                page.wait_for_timeout(5000)
            try:
                page.wait_for_url(re.compile(rf".*blog\.naver\.com/{blog_id}/\d+.*"), timeout=25000)
                result["ok"] = True
                result["url"] = page.url
                print("발행 완료:", page.url)
            except Exception:
                # URL 패턴 불일치 시: 블로그 메인에서 제목으로 재확인
                try:
                    page.goto(f"https://blog.naver.com/{blog_id}", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    found = False
                    for f in page.frames:
                        try:
                            if f.locator(f"text={post['title'][:20]}").count():
                                found = True
                                break
                        except Exception:
                            continue
                    if found:
                        result["ok"] = True
                        result["url"] = f"https://blog.naver.com/{blog_id}"
                        print("발행 완료 (메인에서 제목 확인):", post["title"])
                    else:
                        page.screenshot(path=os.path.join(BASE, "publish_state.png"))
                        result["ok"] = False
                        print("발행 결과 불확실 — publish_state.png 확인")
                except Exception:
                    page.screenshot(path=os.path.join(BASE, "publish_state.png"))
                    result["ok"] = False
                    print("발행 결과 불확실 — publish_state.png 확인")
        return result
    finally:
        _sleep(500, 1000)
        browser.close()
        pw.stop()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    if cmd == "login":
        login(headed=True)
    elif cmd == "check":
        pw, browser, ctx, page = launch(headless=True)
        print("로그인 상태:", is_logged_in(page))
        browser.close(); pw.stop()
