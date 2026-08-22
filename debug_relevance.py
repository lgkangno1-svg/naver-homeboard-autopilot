# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from images import _to_en, _is_relevant, _VISION_BUDGET
import llm, base64

q = "생물 꽃게 스티로폼 포장 박스 개봉"
print("영어 번역:", repr(_to_en(q)))
data = open("downloads/qtest_0.jpg", "rb").read()
_VISION_BUDGET["n"] = 0
b64 = base64.b64encode(data).decode()
try:
    out = llm.vision(
        f"data:image/jpeg;base64,{b64}",
        f"이 사진이 '{q}'라는 주제와 관련이 있으면 yes, 없으면 no만 출력해.",
        max_tokens=3000)
except Exception as e:
    out = "ERR: " + str(e)[:200]
print("비전 응답:", repr(out))
print("판정:", _is_relevant(data, q))
