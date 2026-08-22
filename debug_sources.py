# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from images import _commons_urls, _openverse_urls, _naver_shopping_urls

print("== commons ==")
u1 = _commons_urls("grocery shopping korea", want=3)
print(len(u1), u1[:2])
print("== openverse ==")
u2 = _openverse_urls("supermarket groceries", want=3)
print(len(u2), u2[:2])
print("== naver_shopping ==")
u3 = _naver_shopping_urls("구강세정기", want=3)
print(len(u3), [x[:80] for x in u3[:2]])
