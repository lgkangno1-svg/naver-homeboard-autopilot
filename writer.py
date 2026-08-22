# -*- coding: utf-8 -*-
"""홈판 최적화 글 생성기.
analysis.json(샘플 실측 규칙) + config.json(주제)을 읽어
홈판 노출 글 형식으로 제목/본문/이미지 배치 계획을 생성한다.
"""
import json, os, random, sys

import llm

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))

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

    sysmsg = (
        f"너는 네이버 블로그 '{cfg['topic']['name']}' 분야 10년차 전문 블로거다. "
        "홈판(네이버 홈 피드)에 자주 노출되는 글을 쓴다. 실제 사람이 쓴 것처럼 자연스럽게 쓰고, "
        "AI가 쓴 것 같은 뻔한 표현(목차 나열형, '~했습니다' 연속 반복, 광고 결론)을 쓰지 않는다. "
        "과장·낚시 없이 내용 중심으로 호기심을 유발하는 전개를 한다."
    )
    user = f"""
1단계: 아래 키워드 힌트와 최근 제목 목록을 보고 '최근에 안 다룬' 구체적 소재 1개를 정한다.
키워드 힌트: {kw}
{recent_block}

2단계: 그 소재로 글을 작성한다.

[제목 규칙]
- {tmin}~{tmax}자 (공백 포함)
- 형식: “따옴표 훅 구문” 숫자표현 + 핵심 사건/정보 서술, {int(rules['title_question_end_ratio']*100)}% 확률로 의문형 종결
- 예시 스타일: “후배를 믿는다” 8년 함께한 강호동 하차, 세 맹버 합류가 바꿔 분위기는?
- 중요: 제목 안의 따옴표는 반드시 유니코드 “ ” 를 사용 (ASCII 쌍따옴표 사용 금지 — JSON이 깨짐)
- 핵심 키워드를 제목 앞쪽 절반에 배치

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

[이미지 계획] 총 {imin}~{imax}장 — 첫 장은 대표(제목 아래), 이후 섹션 경계마다. 위치별 이미지 검색용 한국어 쿼리 작성

JSON으로만 답해:
{{"angle": "소재 한 줄", "keyword": "핵심 검색키워드",
"title": "...", "intro": ["..."], "sections": [{{"heading": "...", "paragraphs": ["..."], "emphasis": "...", "centered_lines": ["..."]}}],
"conclusion": ["..."], "image_queries": ["...", "..."]}}
"""
    last_errs = []
    for attempt in range(3):
        post = llm.chat_json([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                             max_tokens=8000, temperature=0.9)
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
