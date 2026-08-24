# -*- coding: utf-8 -*-
"""홈판 최적화 글 생성기.
analysis.json(샘플 실측 규칙) + config.json(주제)을 읽어
홈판 노출 글 형식으로 제목/본문/이미지 배치 계획을 생성한다.
"""
import json, os, random, sys

import llm

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))

# AI스러운 표현 금지 목록 (비평/재생성 기준에 사용)
BANNED_PHRASES = [
    "알아보겠습니다", "알아보았습니다", "정리해 보았습니다", "결론적으로",
    "다양한", "중요한 것은", "참고하세요", "도움이 되었으면", "끝까지",
    "오늘은", "함께 알아보겠습니다", "체크해보세요", "주의하세요",
]

STYLE_EXAMPLES = None


def load_style_examples():
    """실제 홈판 성공 샘플 본문 2개를 few-shot으로 추출"""
    global STYLE_EXAMPLES
    if STYLE_EXAMPLES is not None:
        return STYLE_EXAMPLES
    exs = []
    p = os.path.join(BASE, "samples_extracted.json")
    if os.path.exists(p):
        try:
            data = json.load(open(p, encoding="utf-8"))
            bodies = [x["body_text"] for x in data
                      if x.get("body_text") and len(x.get("body_text", "")) > 200]
            bodies.sort(key=len, reverse=True)
            for b in bodies[:2]:
                exs.append(b[:500])
        except Exception:
            pass
    STYLE_EXAMPLES = exs
    return STYLE_EXAMPLES


def fetch_context(keyword):
    """네이버 검색 결과(제목들+가격)를 실시간 수집해 글의 사실 근거로 주입. 실패 시 빈 문자열."""
    try:
        from playwright.sync_api import sync_playwright
        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})
            pg.goto(f"https://search.naver.com/search.naver?query={keyword}",
                    wait_until="domcontentloaded", timeout=20000)
            pg.wait_for_timeout(2500)
            txt = pg.evaluate("() => document.body.innerText")
            b.close()
        lines = [l.strip() for l in txt.split("\n") if 12 < len(l.strip()) < 70]
        # 링크/제목처럼 보이는 줄 우선
        heads = [l for l in lines if not l.replace(",", "").replace(".", "").isdigit()][:10]
        import re as _re
        prices = _re.findall(r"[12][0-9]{0,2}(?:,[0-9]{3})+(?:\.[0-9]+)?\s*원", txt)[:6]
        ctx = ""
        if heads:
            ctx += "[네이버 검색 상위 결과 제목 — 현재 사람들이 보는 정보]\n"
            ctx += "\n".join(f"- {h}" for h in heads[:8]) + "\n"
        if prices:
            ctx += f"[검색된 실제 가격대] {', '.join(prices)}\n"
        return ctx
    except Exception as e:
        print("  컨텍스트 수집 실패(무시):", str(e)[:80])
        return ""

DEFAULT_RULES = {
    "title_len": [22, 34],
    "title_quote_start_ratio": 0.7,      # 제목이 따옴표 훅으로 시작하는 비율
    "title_digit_ratio": 0.8,            # 제목에 숫자 포함 비율
    "title_question_end_ratio": 0.5,     # 의문형 종결 비율
    "body_chars": [1500, 2500],
    "intro_paragraphs": [2, 3],
    "section_count": [3, 4],
    "section_heading_numbered_ratio": 0.7,
    "paragraph_max_sentences": 3,
    "image_count": [3, 5],
    "image_after_title": True,
    "emphasis_per_section": 1,
    "centered_line_usage": "섹션 사이 전환부에 1~2회",
    "endings": ["~는데요", "~습니다", "~됐는데요", "~더라고요"],
}


def load_rules():
    p = os.path.join(BASE, "analysis.json")
    if os.path.exists(p):
        try:
            data = json.load(open(p, encoding="utf-8"))
            return {**DEFAULT_RULES, **data.get("rules", {})}
        except Exception:
            pass
    return dict(DEFAULT_RULES)


def load_config():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def recent_titles(n=60):
    p = os.path.join(BASE, "logs", "published.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(line).get("title", ""))
        except Exception:
            pass
    return out[-n:]


def validate(post, cfg, rules):
    errs = []
    t = post.get("title", "")
    tmin, tmax = rules["title_len"]
    if not (tmin <= len(t) <= tmax + 6):
        errs.append(f"제목 길이 {len(t)}")
    body_text = "".join(post.get("intro", []))
    for s in post.get("sections", []):
        body_text += "".join(s.get("paragraphs", [])) + s.get("heading", "") + (s.get("emphasis") or "")
        body_text += "".join(s.get("centered_lines") or [])
    body_text += "".join(post.get("conclusion", []))
    cmin, cmax = rules["body_chars"]
    if len(body_text) < cmin * 0.85:
        errs.append(f"본문 부족 {len(body_text)}자")
    qn = len(post.get("image_queries", []))
    if qn < rules["image_count"][0]:
        errs.append(f"이미지 쿼리 부족 {qn}")
    return errs, len(body_text)


def score_title(t, rules):
    """규칙 기반 제목 점수 (높을수록 좋음)"""
    s = 0
    tmin, tmax = rules["title_len"]
    if tmin <= len(t) <= tmax:
        s += 2
    elif tmin - 4 <= len(t) <= tmax + 6:
        s += 1
    if any(c in t for c in "\"“”"):
        s += 2
        if t.strip().startswith(("\"", "“")):
            s += 1
    import re as _re
    m = _re.search(r"\d", t)
    if m:
        s += 2
        if m.start() / max(1, len(t)) <= rules["title_digit_pos"] + 0.15:
            s += 1
    if t.rstrip().endswith("?"):
        s += 1
    for b in BANNED_PHRASES:
        if b in t:
            s -= 3
    return s


def pick_best_title(candidates, rules):
    scored = sorted(((score_title(t, rules), t) for t in candidates), reverse=True)
    return scored[0][1], scored


def critique_post(post):
    """LLM 비평: 품질 점수(10점 만점)와 개선점 반환"""
    body_text = "\n".join(post.get("intro", []))
    for s in post.get("sections", []):
        body_text += "\n" + s.get("heading", "") + "\n" + "\n".join(s.get("paragraphs", []))
        if s.get("emphasis"):
            body_text += "\n[강조] " + s["emphasis"]
    body_text += "\n" + "\n".join(post.get("conclusion", []))
    res = llm.chat_json([
        {"role": "system", "content":
            "너는 네이버 홈판 상위노출 전문 편집자다. 아래 글을 혹평한다. "
            "AI가 썼다는 걸 알아채게 하는 표현, 뻔한 전개, 구체성 부족, 후킹 약한 문장을 잡아낸다."},
        {"role": "user", "content":
            f"[제목]\n{post['title']}\n\n[본문]\n{body_text[:3000]}\n\n"
            'JSON으로만: {"scores": {"hook": 0-10, "specificity": 0-10, "naturalness": 0-10, '
            '"structure": 0-10}, "problems": ["문제점 요약들"], "fix_instructions": ["재작성 시 반영 지시들"]}'},
    ], max_tokens=2000, temperature=0.3)
    return res


def generate_post(seed_hint=None):
    """각도 선택 + 본문 생성을 단일 호출로 처리 (속도 최적화)"""
    cfg = load_config()
    rules = load_rules()
    recent = recent_titles()
    kw = random.sample(cfg["topic"]["keywords"], k=min(4, len(cfg["topic"]["keywords"])))
    cmin, cmax = rules["body_chars"]
    imin, imax = rules["image_count"]
    tmin, tmax = rules["title_len"]
    smin, smax = rules["section_count"]
    recent_block = ("최근 다룬 제목 (중복 금지):" + chr(10).join(recent[-25:])) if recent else ""
    examples = load_style_examples()
    example_block = ""
    if examples:
        example_block = ("[실제 홈판에 노출된 성공 글 스타일 예시 — 이 어투와 리듬을 참고하되 내용은 복사 금지]\n"
                         + "\n---\n".join(examples) + "\n")
    sysmsg = (
        f"너는 네이버 블로그 '{cfg['topic']['name']}' 분야 10년차 전문 블로거다. "
        "홈판(네이버 홈 피드)에 자주 노출되는 글을 쓴다. 실제 사람이 쓴 것처럼 자연스럽게 쓰고, "
        "AI가 쓴 것 같은 뻔한 표현(목차 나열형, '~했습니다' 연속 반복, 광고 결론)을 쓰지 않는다. "
        "과장·낚시 없이 내용 중심으로 호기심을 유발하는 전개를 한다."
    )

    last_errs = []
    for attempt in range(3):
        # 1) 소재+본문 생성 (실시간 컨텍스트 주입)
        context = fetch_context(kw[0]) if attempt == 0 else ""
        user = f"""
1단계: 아래 키워드 힌트와 최근 제목 목록을 보고 '최근에 안 다룬' 구체적 소재 1개를 정한다.
키워드 힌트: {kw}
{recent_block}

{context}
{example_block}
2단계: 그 소재로 글을 작성한다.

[제목 규칙]
- {tmin}~{tmax}자 (공백 포함)
- 형식: “따옴표 훅 구문” 숫자표현 + 핵심 사건/정보 서술, {int(rules['title_question_end_ratio']*100)}% 확률로 의문형 종결
- 예시 스타일: “후배를 믿는다” 8년 함께한 강호동 하차, 세 맹버 합류가 바꿔 분위기는?
- 중요: 제목 안의 따옴표는 반드시 유니코드 “ ” 를 사용 (ASCII 쌍따옴표 사용 금지 — JSON이 깨짐)
- 숫자는 제목 전체 길이의 앞쪽 40% 안에 배치 (따옴표 훅 안에 넣거나 바로 뒤에)
- 핵심 키워드를 제목 앞쪽 절반에 배치
- 제목 후보 4개를 만들고 그중 가장 클릭하고 싶은 것을 title로

[본문 규격]
- 전체 {cmin}~{cmax}자 (공백 포함)
- intro: {rules['intro_paragraphs'][0]}~{rules['intro_paragraphs'][1]}개 문단, 첫 문장에 키워드 포함
- sections: {smin}~{smax}개. 각 섹션:
  - heading: 문장형 소제목 25자 내외 ({int(rules['section_heading_numbered_ratio']*100)}% 확률로 "1." 식 번호 포함)
  - paragraphs: 2~4개 문단 (문단당 1~3문장, 짧게 끊기)
  - emphasis: 섹션에서 가장 중요한 한 문장
  - centered_lines: 섹션 중 1곳만, 여운 있는 짧은 한 줄 2~3개
- conclusion: 1~2문단, 전망/정리 + 독자 반응 유도 가능
- 어미 다양화: ~는데요, ~습니다, ~더라고요, ~됐는데요 섞기
- 숫자(연도/횟수/수치)를 초반과 중간에 자연스럽게 배치

[가독성 규칙 — 모바일 홈판 기준]
- 한 문단은 1~2문장. 한 문장 안에 쉼표 2개 이상 금지 (줄바꿈으로 분리)
- 한 줄은 40자 이내로 끊어쓰기. 군더더기 조사 반복 금지
- 문단 사이에 숨 쉴 공간이 느껴지게 배치

[구체성 필수]
- 위 [네이버 검색 결과]의 실제 정보(가격/제품명/이슈)를 본문에 자연스럽게 녹일 것
- 금지 표현: {', '.join(BANNED_PHRASES[:8])} 등 AI 뻔한 표현
- 실제 경험한 사람의 디테일(장소, 상황, 수치)을 넣어 생생하게

[이미지 계획] 총 {imin}~{imax}장 — 첫 장은 대표(제목 아래), 이후 섹션 경계마다. 위치별 이미지 검색용 한국어 쿼리 작성

JSON으로만 답해:
{{"angle": "소재 한 줄", "keyword": "핵심 검색키워드",
"title_candidates": ["...", "...", "...", "..."],
"title": "...", "intro": ["..."], "sections": [{{"heading": "...", "paragraphs": ["..."], "emphasis": "...", "centered_lines": ["..."]}}],
"conclusion": ["..."], "image_queries": ["...", "..."]}}
"""
        post = llm.chat_json([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                             max_tokens=8000, temperature=0.9)
        # 2) 제목 후보 중 최선 선택
        cands = post.get("title_candidates") or [post.get("title", "")]
        best, _scored = pick_best_title([c for c in cands if c], rules)
        post["title"] = best
        # 3) 비평 패스 — 점수 낮으면 지시 반영해 1회 재작성
        try:
            crit = critique_post(post)
            scores = crit.get("scores", {})
            avg = sum(float(v) for v in scores.values()) / max(1, len(scores))
            post["_critique"] = {"avg": round(avg, 1), "scores": scores}
            if avg < 7.0 and attempt < 2:
                fixes = "; ".join(crit.get("fix_instructions", [])[:4])
                print(f"  비평 점수 {avg:.1f}/10 → 재작성 ({fixes[:120]})")
                post = llm.chat_json([
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps(post, ensure_ascii=False)[:6000]},
                    {"role": "user", "content":
                        f"편집자 비평 점수가 {avg:.1f}/10이다. 아래 지시를 반영해 전체를 다시 작성해라. "
                        f"수정 지시: {fixes}\n"
                        f"문제점: {'; '.join(crit.get('problems', [])[:4])}\n"
                        "같은 JSON 스키마로만 답해."},
                ], max_tokens=8000, temperature=0.85)
                cands = post.get("title_candidates") or [post.get("title", "")]
                best, _ = pick_best_title([c for c in cands if c], rules)
                post["title"] = best
        except Exception as e:
            print("  비평 패스 생략:", str(e)[:80])
        errs, chars = validate(post, cfg, rules)
        if not errs:
            post["_chars"] = chars
            post["_angle"] = {"angle": post.get("angle", ""), "keyword": post.get("keyword", "")}
            return post
        last_errs = errs
    raise RuntimeError(f"글 규격 미달 3회: {last_errs}")


if __name__ == "__main__":
    post = generate_post()
    print(json.dumps(post, ensure_ascii=False, indent=1)[:3000])
