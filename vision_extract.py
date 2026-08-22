# -*- coding: utf-8 -*-
"""스크린샷 70장을 stealth/ox-alpha 비전으로 구조화 추출 -> samples_extracted.json (증분 저장)"""
import base64, glob, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

KEY = os.environ["OPENROUTER_API_KEY"]
API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "stealth/ox-alpha"

PROMPT = """이것은 네이버 블로그/홈판에 노출된 글의 스크린샷입니다. 보이는 내용을 정확히 JSON으로 추출하세요.
{
 "kind": "header|body|footer|feed_list|other",
 "title": "제목 전체 텍스트 (제목이 안 보이면 null)",
 "body_text": "보이는 본문 텍스트 전체 (광고/UI/메뉴 제외, 순수 글 본문만. 없으면 null)",
 "visible_photos": 0,
 "subheadings": ["굵은 글씨 소제목들"],
 "colored_emphasis": false,
 "centered_lines": false,
 "has_divider": false
}
설명 없이 JSON만 출력하세요."""

def img_b64(path, max_w=900):
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()

def extract(path):
    for attempt in range(4):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64(path)}"}},
                        {"type": "text", "text": PROMPT}]}],
                    "temperature": 0, "max_tokens": 3000,
                }, timeout=240)
            if r.status_code == 429:
                time.sleep(8 * (attempt + 1)); continue
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            txt = (msg.get("content") or "") or ""
            m = re.search(r"\{.*\}", txt, re.S)
            data = json.loads(m.group()) if m else {"_raw": txt[:200]}
            data["_file"] = path
            return data
        except Exception as e:
            if attempt == 3:
                return {"_file": path, "_error": str(e)[:200]}
            time.sleep(5)

files = sorted(glob.glob("samples/*/*"))
# 재개 모드: 이미 성공한 파일은 건너뜀
prev = []
if os.path.exists("samples_extracted.json"):
    try:
        prev = json.load(open("samples_extracted.json", encoding="utf-8"))
    except Exception:
        prev = []
done_files = {p["_file"] for p in prev if not p.get("_error")}
todo = [f for f in files if f.replace("\\", "/") not in {d.replace("\\", "/") for d in done_files}]
print(f"대상 {len(files)}장 / 미처리 {len(todo)}장")
results = list(prev)
errs = 0
with ThreadPoolExecutor(max_workers=3) as ex:
    futs = {ex.submit(extract, f): f for f in todo}
    done = 0
    for fut in as_completed(futs):
        res = fut.result()
        results.append(res)
        if res.get("_error"): errs += 1
        done += 1
        print(f"[{done}/{len(todo)}] {os.path.basename(res['_file'])} kind={res.get('kind','?')} title={str(res.get('title'))[:36]}", flush=True)
        if done % 5 == 0:
            json.dump(results, open("samples_extracted.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump(results, open("samples_extracted.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"완료: {len(results)}건 (오류 {errs}) -> samples_extracted.json")
