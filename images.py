# -*- coding: utf-8 -*-
"""이미지 소싱 + 워터마크.
소스 정책 (config.image_sources 순서):
  - wikimedia_commons : 위키미디어 공용 (자유 라이선스) — 기본
  - openverse         : CC 라이선스 통합 검색 (Openverse API, 키 불필요)
  - naver_shopping    : 네이버 쇼핑 상품 썸네일 (상품/쇼핑 정보 글 전용으로만 사용 권장)
  - local_pool        : 사용자가 images_pool/ 에 직접 넣은 사진
※ 타인의 블로그 이미지 무단 수집은 하지 않는다.

워터마크 (config.watermark):
  mode: text | image | both | none
"""
import hashlib, io, json, os, random, sys, time

import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _load_cfg():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def _download(url, timeout=20):
    for attempt in range(2):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 15))
                time.sleep(min(wait, 30))
                continue
            if r.status_code != 200 or len(r.content) < 8000:
                return None
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width < 500 or im.height < 350:
                return None
            return im
        except Exception:
            return None
    return None


def _placeholder_image(text):
    """모든 소스 실패 시 사용할 브랜드 플레이스홀더 이미지."""
    W, H = 1080, 720
    im = Image.new("RGB", (W, H), (246, 247, 250))
    d = ImageDraw.Draw(im)
    for i in range(H):  # 은은한 그라데이션
        c = 246 - int(i / H * 18)
        d.line([(0, i), (W, i)], fill=(c, c, c + 4))
    fs = max(28, int(W * 0.05))
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, H / 2 - fs), text[:20], font=font, fill=(90, 98, 110))
    cfg = _load_cfg()
    im = apply_watermark(im, cfg)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------------- 소스별 URL 수집 ----------------

def _commons_urls(query, want=6):
    """위키미디어 공용: 자유 라이선스 이미지"""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "generator": "search",
            "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": want * 2,
            "prop": "imageinfo", "iiprop": "url|size|mime",
            "iiurlwidth": 1080, "format": "json",
        }, headers={"User-Agent": "blog-automation/1.0 (contact: local)"}, timeout=20)
        if r.status_code != 200:
            time.sleep(10)
            return []
        items = (r.json().get("query", {}) or {}).get("pages", {})
        out = []
        for v in items.values():
            ii = (v.get("imageinfo") or [{}])[0]
            if ii.get("mime", "").startswith("image/") and ii.get("width", 0) >= 600:
                out.append(ii.get("thumburl") or ii.get("url"))
        return [u for u in out if u][:want]
    except Exception as e:
        print("  commons 실패:", str(e)[:80])
        return []


def _openverse_urls(query, want=6):
    """Openverse: CC 라이선스 이미지 통합 검색 (익명 허용량 있음)"""
    try:
        r = requests.get("https://api.openverse.org/v1/images/", params={
            "q": query, "page_size": want * 2,
            "license_type": "commercial,modification",
            "size": "large",
        }, headers={"User-Agent": "blog-automation/1.0"}, timeout=20)
        if r.status_code != 200:
            return []
        out = []
        for item in r.json().get("results", []):
            u = item.get("url") or item.get("thumbnail")
            w = item.get("width") or 0
            if u and w >= 600:
                out.append(u)
        return out[:want]
    except Exception as e:
        print("  openverse 실패:", str(e)[:80])
        return []


def _naver_shopping_urls(query, want=6):
    """네이버 쇼핑 상품 썸네일 (상품 정보 글 전용). 카탈로그/판매자 제공 썸네일."""
    from urllib.parse import urlparse, parse_qs, unquote
    urls = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})
            pg.goto(f"https://search.shopping.naver.com/search/all?query={query}",
                    wait_until="networkidle", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.mouse.wheel(0, 1200)
            pg.wait_for_timeout(4000)
            srcs = pg.evaluate(
                """() => Array.from(document.querySelectorAll('img'))
                    .map(i => i.src || '')
                    .filter(s => /^https?:/.test(s)
                                 && (/shopping-phinf\\.pstatic\\.net/.test(s)
                                     || (/search\\.pstatic\\.net\\/common\\//.test(s) && s.includes('src=')))
                                 && !s.includes('/static/'))""")
            b.close()
        seen = set()
        for s in srcs:
            # 썸네일 프록시면 원본 추출 시도, 아니면 그대로 사용
            if "search.pstatic.net" in s:
                qs = parse_qs(urlparse(s).query)
                orig = qs.get("src", [None])[0]
                if orig:
                    s = unquote(orig)
            if s.startswith("http") and s not in seen:
                seen.add(s)
                urls.append(s)
    except Exception as e:
        print("  shopping 실패:", str(e)[:80])
    return urls[:want]


def _local_pool(query, want=4):
    pool = os.path.join(BASE, _load_cfg().get("local_pool_dir", "images_pool"))
    if not os.path.isdir(pool):
        return []
    files = [os.path.join(pool, f) for f in os.listdir(pool)
             if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    random.shuffle(files)
    return files[:want]


_TOSS_CACHE = None


def _toss_products(query, want=6):
    """로컬 토스쇼핑 상품 데이터(hypeduck_audit)에서 상품 썸네일 매칭.
    판매자/카탈로그 제공 썸네일만 사용."""
    global _TOSS_CACHE
    if _TOSS_CACHE is None:
        _TOSS_CACHE = []
        import re as _re
        for f in ["hypeduck_audit/category_main_products.json", "hypeduck_audit/product_samples.json"]:
            try:
                d = json.load(open(os.path.join(BASE, f), encoding="utf-8"))
                items = []
                if isinstance(d, dict):
                    for v in d.values():
                        if isinstance(v, list):
                            items += [p for p in v if isinstance(p, dict)]
                elif isinstance(d, list):
                    items = [p for p in d if isinstance(p, dict)]
                _TOSS_CACHE += [p for p in items if p.get("image")]
            except Exception:
                pass
    toks = [t for t in query.split() if len(t) >= 2]
    scored = [p for p in _TOSS_CACHE if any(t in p.get("title", "") for t in toks)]
    if not scored:
        scored = _TOSS_CACHE
    random.shuffle(scored)
    return [p["image"] for p in scored[:want]]


SOURCES = {
    "wikimedia_commons": _commons_urls,
    "openverse": _openverse_urls,
    "naver_shopping": _naver_shopping_urls,
    "toss_products": _toss_products,
    "local_pool": _local_pool,
}

# ---------------- 워터마크 ----------------

POS = {
    "bottom-right": lambda W, H, tw, th, pad: (W - tw - pad * 2, H - th - pad * 2),
    "bottom-left": lambda W, H, tw, th, pad: (pad * 2, H - th - pad * 2),
    "top-right": lambda W, H, tw, th, pad: (W - tw - pad * 2, pad * 2),
    "top-left": lambda W, H, tw, th, pad: (pad * 2, pad * 2),
    "center": lambda W, H, tw, th, pad: ((W - tw) // 2, (H - th) // 2),
}


def _apply_text_wm(im, wcfg):
    text = wcfg.get("text", "")
    if not text:
        return im
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fs = max(18, int(im.width * wcfg.get("font_size_ratio", 0.035)))
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = int(fs * 0.5)
    x, y = POS.get(wcfg.get("position", "bottom-right"), POS["bottom-right"])(im.width, im.height, tw, th, pad)
    col = tuple(wcfg.get("text_color", [255, 255, 255]))
    alpha = int(255 * wcfg.get("opacity", 0.45))
    if wcfg.get("background_strip", True):
        d.rectangle([x - pad // 2, y - pad // 2, x + tw + pad * 3 // 2, y + th + pad], fill=(0, 0, 0, 70))
    d.text((x, y), text, font=font, fill=col + (alpha,))
    return Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")


def _apply_image_wm(im, wcfg):
    path = os.path.join(BASE, wcfg.get("image_path", "watermark.png"))
    if not os.path.exists(path):
        print(f"  [경고] 워터마크 이미지 없음: {path}")
        return im
    wm = Image.open(path).convert("RGBA")
    scale = wcfg.get("image_scale_ratio", 0.18)
    nw = max(24, int(im.width * scale))
    wm = wm.resize((nw, int(wm.height * nw / wm.width)), Image.LANCZOS)
    if wcfg.get("opacity", 0.45) < 1:
        a = wm.split()[3].point(lambda v: int(v * wcfg.get("opacity", 0.45)))
        wm.putalpha(a)
    pad = int(im.width * 0.02)
    pos = wcfg.get("position", "bottom-right")
    x, y = {
        "bottom-right": (im.width - wm.width - pad, im.height - wm.height - pad),
        "bottom-left": (pad, im.height - wm.height - pad),
        "top-right": (im.width - wm.width - pad, pad),
        "top-left": (pad, pad),
        "center": ((im.width - wm.width) // 2, (im.height - wm.height) // 2),
    }.get(pos, (im.width - wm.width - pad, im.height - wm.height - pad))
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    layer.paste(wm, (x, y), wm)
    return Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")


def apply_watermark(im, cfg):
    wcfg = cfg.get("watermark", {})
    mode = wcfg.get("mode", "text" if wcfg.get("enabled", True) else "none")
    if mode in ("text", "both"):
        im = _apply_text_wm(im, wcfg)
    if mode in ("image", "both"):
        im = _apply_image_wm(im, wcfg)
    return im


def process(im, cfg):
    max_w = 1080
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
    im = ImageEnhance.Sharpness(im).enhance(1.08)
    im = apply_watermark(im, cfg)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=86)
    return buf.getvalue()


_EN_CACHE = {}


def _to_en(query):
    """한국어 쿼리를 영어 이미지 검색용으로 변환 (캐시). 실패 시 원본 반환."""
    if query in _EN_CACHE:
        return _EN_CACHE[query]
    try:
        import llm
        out = llm.chat(
            [{"role": "user", "content":
                f"Translate this Korean image-search query to a short English photo search query (2-4 words). "
                f"Answer with the English query only: {query}"}],
            max_tokens=500, temperature=0)
        en = out.strip().strip('"').splitlines()[0][:60]
        _EN_CACHE[query] = en or query
        return _EN_CACHE[query]
    except Exception:
        return query


def fetch_images(queries, count, tag="post"):
    """쿼리 리스트 순서대로 count장 확보. 한국어 쿼리가 안 통하면 영어 번역으로 재시도."""
    cfg = _load_cfg()
    sources = [s for s in cfg.get("image_sources", ["wikimedia_commons"]) if s in SOURCES]
    got, seen = [], set()

    def try_query(q):
        urls = []
        for sname in sources:
            urls += SOURCES[sname](q, want=5)
            if len(urls) >= 4:
                break
        random.shuffle(urls)
        for u in urls[:4]:
            if len(got) >= count:
                return
            h = hashlib.md5(str(u).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            im = _download(u) if str(u).startswith("http") else Image.open(u).convert("RGB")
            if im is None:
                continue
            got.append((q, process(im, cfg)))
            time.sleep(random.uniform(0.4, 1.2))

    for q in queries:
        if len(got) >= count:
            break
        before = len(got)
        try_query(q)
        if len(got) == before:  # 한국어 쿼리 실패 → 영어 재시도
            try_query(_to_en(q))
    # 그래도 부족하면 플레이스홀더로 보완 (발행이 이미지 때문에 막히지 않게)
    while len(got) < count:
        got.append(("placeholder", _placeholder_image(queries[0] if queries else "알뜰정보")))
    return got[:count]


if __name__ == "__main__":
    res = fetch_images(["현대 그랜저"], 2)
    os.makedirs("downloads", exist_ok=True)
    for i, (q, data) in enumerate(res):
        open(f"downloads/wm_test_{i}.jpg", "wb").write(data)
        print(f"저장 downloads/wm_test_{i}.jpg ({len(data)//1024}KB) query={q}")
