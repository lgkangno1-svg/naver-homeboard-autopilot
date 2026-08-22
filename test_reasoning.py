# -*- coding: utf-8 -*-
"""ox-alpha reasoning 파라미터별 속도/품질 테스트"""
import os, sys, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
key = os.environ["OPENROUTER_API_KEY"]
H = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

CASES = [
    ("기본", {}),
    ("reasoning_low", {"reasoning": {"effort": "low"}}),
    ("reasoning_off", {"reasoning": {"enabled": False}}),
]
for label, extra in CASES:
    t0 = time.time()
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=H, timeout=240, json={
            "model": "stealth/ox-alpha", "max_tokens": 2500, **extra,
            "messages": [{"role": "user", "content": "전기차 배터리 보증에 대해 한국어로 3문단 설명해줘. 약 600자."}]})
        d = r.json()
        c = (d["choices"][0]["message"].get("content") or "")
        u = d.get("usage", {})
        rt = u.get("completion_tokens_details", {}).get("reasoning_tokens")
        print(f"{label}: {time.time()-t0:.0f}초 / content {len(c)}자 / completion {u.get('completion_tokens')} tok / reasoning {rt} tok")
    except Exception as e:
        print(label, "실패:", str(e)[:120])
