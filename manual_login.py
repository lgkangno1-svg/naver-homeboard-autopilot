# -*- coding: utf-8 -*-
"""Windows/desktop manual Naver login helper.

Always opens a visible browser, ignores HEADLESS and NAVER_ID/NAVER_PW,
and saves Playwright storage state after the user completes login manually.
"""
import os
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "storage_state.json")
LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_HOME = "https://www.naver.com/"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _looks_logged_in(page):
    """Return True once the browser has left Naver's login flow."""
    url = (page.url or "").lower()
    if "nid.naver.com" in url and ("login" in url or "nidlogin" in url):
        return False
    # A successful login normally redirects away from nid.naver.com.
    return "naver.com" in url


def main(timeout_minutes=15):
    print("=== 네이버 수동 로그인 ===")
    print("브라우저가 열리면 직접 네이버에 로그인하세요.")
    print("2단계 인증/캡차가 나오면 브라우저에서 직접 완료하면 됩니다.")
    print("로그인이 끝나면 이 프로그램이 자동으로 세션을 저장합니다.")
    print("브라우저 창을 직접 닫지 마세요.\n")

    with sync_playwright() as pw:
        channel = os.getenv("BROWSER_CHANNEL", "chrome").strip() or "chrome"
        args = ["--disable-blink-features=AutomationControlled", "--start-maximized"]
        try:
            browser = pw.chromium.launch(headless=False, channel=channel, args=args)
        except Exception:
            print(f"브라우저 채널 '{channel}' 실행 실패 → Playwright Chromium으로 재시도")
            browser = pw.chromium.launch(headless=False, args=args)

        context = browser.new_context(
            viewport=None,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=40000)

        deadline = time.time() + max(1, timeout_minutes) * 60
        last_notice = 0
        success = False

        while time.time() < deadline:
            # If a successful redirect occurred, verify by opening Naver home once.
            if _looks_logged_in(page):
                try:
                    page.goto(NAVER_HOME, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)
                    if "nid.naver.com" not in (page.url or "").lower():
                        success = True
                        break
                except Exception:
                    pass

            elapsed = int(deadline - time.time())
            if time.time() - last_notice >= 15:
                print(f"로그인 완료 대기 중... 남은 시간 약 {max(0, elapsed // 60)}분")
                last_notice = time.time()
            page.wait_for_timeout(1000)

        if not success:
            try:
                page.screenshot(path=os.path.join(BASE, "login_failed.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            raise RuntimeError(
                "15분 안에 로그인 완료를 확인하지 못했습니다. "
                "브라우저에서 로그인 후 리다이렉트가 끝날 때까지 기다려 주세요."
            )

        context.storage_state(path=STATE)
        print("\n로그인 성공!")
        print("세션 저장:", STATE)
        print("이 파일을 미니PC의 ~/blogbot/storage_state.json 으로 복사하면 됩니다.")
        page.wait_for_timeout(1200)
        browser.close()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자가 취소했습니다.")
        raise SystemExit(130)
    except Exception as e:
        print("\n로그인 도구 오류:", e)
        raise SystemExit(1)
