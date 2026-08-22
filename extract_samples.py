# -*- coding: utf-8 -*-
"""docx 속 스크린샷을 문서 내 등장 순서대로 추출 -> samples/<문서명>/NN.ext"""
import glob, os, re, sys, zipfile

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\Users\tnfwo\Desktop\홈판분석"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

files = sorted(glob.glob(os.path.join(SRC, "*.docx")))
total = 0
for f in files:
    name = os.path.splitext(os.path.basename(f))[0]
    safe = re.sub(r"[^\w\-가-힣 ]", "_", name).strip()[:40]
    outdir = os.path.join(DST, safe)
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(f) as z:
        # 관계 ID -> 미디어 파일 매핑
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        rid2file = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]*media/[^"]+)"', rels))
        # 문서 본문에서 등장 순서대로 r:embed 추출
        docxml = z.read("word/document.xml").decode("utf-8")
        order = [rid2file[rid] for rid in re.findall(r'r:embed="([^"]+)"', docxml) if rid in rid2file]
        seen = {}
        for i, target in enumerate(order, 1):
            path = "word/" + target.lstrip("/")
            ext = os.path.splitext(target)[1].lower() or ".png"
            out = os.path.join(outdir, f"{i:02d}{ext}")
            if out in seen:
                continue
            seen[out] = True
            with z.open(path) as src, open(out, "wb") as dst:
                dst.write(src.read())
            total += 1
    print(f"{safe}: {len(seen)}장 추출")
print(f"총 {total}장 -> {DST}")
