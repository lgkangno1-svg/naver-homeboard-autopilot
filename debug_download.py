# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from images import _download, _naver_shopping_urls

u1 = "https://upload.wikimedia.org/wikipedia/commons/d/de/Interior_of_%22Matkroken%22_Supermarket_grocery_store_in_Leirvik%2C_Stord%2C_Norway_2018-03-10._Cashier_checkout_a.jpg"
im = _download(u1)
print("openverse/commons URL 다운로드:", "OK " + str(im.size) if im else "FAIL")

print("== shopping raw srcs ==")
# 필터 통과 전 원본 src 목록 확인
from playwright.sync_api import sync_playwright
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})
    pg.goto("https://search.shopping.naver.com/search/all?query=%EA%B5%AC%EA%B0%95%EC%84%B8%EC%A0%95%EA%B8%B0",
            wait_until="domcontentloaded", timeout=25000)
    pg.wait_for_timeout(4000)
    srcs = pg.evaluate("""() => Array.from(document.querySelectorAll('img')).map(i => i.src||'').filter(s=>/^https?:/.test(s)).slice(0,20)""")
    b.close()
for s in srcs[:15]:
    print(" -", s[:110])
