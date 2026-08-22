# -*- coding: utf-8 -*-
"""Windows 내장 한국어 OCR + 사진 밴드 감지로 스크린샷 70장 분석 -> samples_ocr.json"""
import asyncio, glob, json, os, statistics, sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

async def ocr_image(path, engine):
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import InMemoryRandomAccessStream
    import winrt.windows.foundation as foundation

    data = open(path, "rb").read()
    stream = InMemoryRandomAccessStream()
    writer = stream.get_output_stream_at(0)
    dw = writer.write_async(foundation.IBuffer(bytes(data)))
    while dw.status == 0:
        await asyncio.sleep(0.01)
    await writer.flush_async()
    writer.dispose()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bmp = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bmp)
    lines = []
    for line in result.lines:
        words = [w.bounding_rect for w in line.words]
        if not words:
            continue
        x0 = min(w.x for w in words); y0 = min(w.y for w in words)
        x1 = max(w.x + w.width for w in words); y1 = max(w.y + w.height for w in words)
        lines.append({"text": line.text, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return lines

def photo_bands(path, text_lines):
    """OCR 텍스트가 없는 '색조도 높은' 세로 구간을 사진으로 간주"""
    im = Image.open(path).convert("RGB")
    W, H = im.size
    small = np.asarray(im.resize((120, max(1, int(H * 120 / W)))), dtype=np.int16)
    sh = small.shape[0]
    scale = H / sh
    sat = (small.max(axis=2) - small.min(axis=2)).mean(axis=1)          # 색 포화 평균
    var = small.std(axis=1)                                             # 행 내 명암 편차
    # 텍스트 마스크
    txt = np.zeros(sh, dtype=bool)
    for l in text_lines:
        y0, y1 = int(l["y"] / scale), int((l["y"] + l["h"]) / scale)
        txt[max(0, y0):min(sh, y1 + 1)] = True
    cand = ((sat > 18) | (var > 45)) & (~txt)
    # 연속 구간 병합
    bands, start = [], None
    for i, c in enumerate(cand):
        if c and start is None: start = i
        elif not c and start is not None:
            bands.append((start, i)); start = None
    if start is not None: bands.append((start, len(cand)))
    # 노이즈 제거: 화면 높이의 6% 이상인 구간만
    return [(int(a * scale), int(b * scale)) for a, b in bands if (b - a) * scale > H * 0.06]

def analyze(path, engine):
    lines = asyncio.run(ocr_image(path, engine))
    bands = photo_bands(path, lines)
    full_text = "\n".join(l["text"] for l in lines)
    body_chars = sum(len(l["text"]) for l in lines)
    # 제목 후보: 이미지 상단 35% 안에서 가장 큰 글자 높이 라인
    H = Image.open(path).height
    heads = [l for l in lines if l["y"] < H * 0.35]
    title = None
    if heads:
        big = max(heads, key=lambda l: l["h"])
        if big["h"] > 28:  # 제목급 큰 글씨
            title = "".join(l["text"] for l in sorted(heads, key=lambda l: l["y"])[:3]) \
                if big["h"] > 45 else big["text"]
    return {
        "file": path.replace("\\", "/"),
        "title": title,
        "text": full_text,
        "char_count": body_chars,
        "line_heights": [round(l["h"], 1) for l in lines],
        "photo_bands": bands,
        "photo_count_est": len(bands),
    }

def main():
    from winrt.windows.media.ocr import OcrEngine
    engine = None
    try:
        from winrt.windows.globalization import Language
        engine = OcrEngine.try_create_from_language(Language("ko-KR"))
    except Exception:
        pass
    engine = engine or OcrEngine.try_create_from_user_profile_language()
    if engine is None:
        print("한국어 OCR 엔진 없음 — 언어팩 필요"); sys.exit(1)
    print("OCR 언어:", engine.recognizer_language.language_tag)

    files = sorted(glob.glob("samples/*/*"))
    out = []
    for i, f in enumerate(files, 1):
        try:
            r = analyze(f, engine)
        except Exception as e:
            r = {"file": f, "_error": str(e)[:150]}
        out.append(r)
        t = (r.get("title") or "")[:40]
        print(f"[{i}/{len(files)}] {os.path.basename(os.path.dirname(f))}/{os.path.basename(f)} "
              f"chars={r.get('char_count','-')} photos={r.get('photo_count_est','-')} title={t}")
    json.dump(out, open("samples_ocr.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"-> samples_ocr.json ({len(out)}건)")

if __name__ == "__main__":
    main()
