# -*- coding: utf-8 -*-
import sys, requests
sys.stdout.reconfigure(encoding="utf-8")

u1 = "https://upload.wikimedia.org/wikipedia/commons/d/de/Interior_of_%22Matkroken%22_Supermarket_grocery_store_in_Leirvik%2C_Stord%2C_Norway_2018-03-10._Cashier_checkout_a.jpg"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
r = requests.get(u1, headers={"User-Agent": UA}, timeout=20)
print("status:", r.status_code, "len:", len(r.content), "type:", r.headers.get("content-type"))
print("body head:", r.text[:200] if "text" in r.headers.get("content-type", "") else "(binary)")
