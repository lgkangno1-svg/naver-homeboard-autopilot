# -*- coding: utf-8 -*-
"""Evidence-aware, quality-gated blog writer.

Compatible with the existing naver.py post schema while reducing fabricated experience,
repetitive AI prose, unsupported numbers and duplicate topics.
"""
import json
import os
import random
import re
from collections import Counter

import llm
import research

BASE = os.path.dirname(os.path.abspath(__file__))

FAKE_EXPERIENCE_PATTERNS = [
    r"\d+\s*(?:일|주|개월|년)\s*(?:써|사용|먹|해)\s*보",
    r"직접\s*(?:써|사용|먹|구매|신청|체험|가|다녀)",
    r"(?:써|사용|먹|신청|체험)해\s*보니",
    r"내돈내산",
    r"실사용\s*후기",
]
AI_PHRASES = [
    "알아보겠습니다", "정리해 보았습니다", "결론적으로", "도움이 되었으면",
    "함께 알아보겠습니다", "끝까지 읽어", "참고하시기 바랍니다",
]


def _cfg():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def _recent_titles(n=80):
    path = os.path.join(BASE, "logs", "published.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("title"):
                    out.append(rec["title"])
            except Exception:
                pass
    except Exception:
        pass
    return out[-n:]


def _post_text(post):
    bits = list(post.get("intro", []))
    for sec in post.get("sections", []):
        bits.append(sec.get("heading", ""))
        bits.extend(sec.get("paragraphs", []))
        if sec.get("emphasis"):
            bits.append(sec["emphasis"])
        bits.extend(sec.get("centered_lines") or [])
    bits.extend(post.get("conclusion", []))
    return "\n".join(x for x in bits if x)


def _deterministic_issues(post, cfg):
    issues = []
    title = post.get("title", "")
    body = _post_text(post)
    quality = cfg.get("quality", {})
    if not 18 <= len(title) <= 40:
        issues.append(f"제목 길이 부적절({len(title)}자)")
    if quality.get("forbid_fabricated_experience", True):
        joined = title + "\n" + body
        for pat in FAKE_EXPERIENCE_PATTERNS:
            if re.search(pat, joined):
                issues.append("근거 없는 직접 체험/사용기간 표현 가능성")
                break
    for phrase in AI_PHRASES:
        if phrase in body:
            issues.append(f"AI 상투어 포함: {phrase}")
    if len(body.replace("\n", "")) < cfg["format"]["char_min"] * 0.85:
        issues.append("본문이 너무 짧음")
    headings = [s.get("heading", "") for s in post.get("sections", [])]
    if len(headings) < 3:
        issues.append("섹션 부족")
    endings = re.findall(r"(습니다|는데요|더라고요|입니다|했어요|됩니다)[.!?]?", body)
    if endings:
        top = Counter(endings).most_common(1)[0][1]
        if top / len(endings) > 0.60 and len(endings) >= 8:
            issues.append("문장 종결 패턴 반복")
    return list(dict.fromkeys(issues))


def _choose_seed(cfg, recent):
    keywords = list(cfg["topic"].get("keywords", []))
    random.shuffle(keywords)
    recent_text = " ".join(recent[-30:])
    fresh = [k for k in keywords if k not in recent_text]
    return (fresh or keywords or [cfg["topic"]["name"]])[0]


def _topic_plan(cfg, seed, evidence, recent):
    prompt = f"""
블로그 주제: {cfg['topic']['name']}
주제 설명: {cfg['topic'].get('description','')}
시드 키워드: {seed}
최근 제목(중복 피하기): {json.dumps(recent[-25:], ensure_ascii=False)}

[검색 화면에서 수집한 참고 스니펫]
{evidence or '- 검색 스니펫 없음'}

아래 원칙으로 오늘 쓸 소재 후보 5개를 만든 뒤 가장 좋은 1개를 고르세요.
- 최근 제목과 사건/효용/질문이 겹치지 않을 것
- 생활자가 실제로 궁금해할 구체적인 문제를 해결할 것
- 검색 스니펫에 없는 가격, 날짜, 통계, 혜택 수치를 지어내지 말 것
- 실제 사용하지 않았는데 '3개월 써봤다', '직접 신청했다', '내돈내산' 같은 체험을 만들지 말 것
- 단순 키워드 나열이 아니라 '왜 지금 읽어야 하는지'가 있는 각도일 것

JSON만 출력:
{{"candidates":[{{"angle":"...","keyword":"...","reader_need":"..."}}],
 "selected":{{"angle":"...","keyword":"...","reader_need":"..."}}}}
"""
    try:
        data = llm.chat_json([
            {"role": "system", "content": "당신은 네이버 생활정보 콘텐츠 편집장입니다. 정확성, 새로움, 독자 효용을 우선합니다."},
            {"role": "user", "content": prompt},
        ], max_tokens=2400, temperature=0.65)
        return data.get("selected") or (data.get("candidates") or [{}])[0]
    except Exception as e:
        print("  소재 계획 실패 → 기본 시드 사용:", str(e)[:90])
        return {"angle": f"{seed}와 관련해 지금 확인할 생활정보", "keyword": seed, "reader_need": "실용 정보"}


def _generation_prompt(cfg, plan, evidence, recent):
    cmin, cmax = cfg["format"]["char_min"], cfg["format"]["char_max"]
    imin, imax = cfg["format"]["image_min"], cfg["format"]["image_max"]
    return f"""
[콘텐츠 브리프]
주제: {cfg['topic']['name']}
핵심 소재: {plan.get('angle','')}
핵심 키워드: {plan.get('keyword','')}
독자 니즈: {plan.get('reader_need','')}
최근 제목: {json.dumps(recent[-20:], ensure_ascii=False)}

[검색 화면 참고 스니펫 - 사실을 단정하기 위한 원문이 아니라 참고 근거]
{evidence or '- 없음. 이 경우 시의성 수치/가격/정책 세부를 새로 만들지 말 것.'}

[절대 규칙]
1. 실제로 하지 않은 경험을 만들지 않는다. '직접 써봤다/3개월 사용/내돈내산/신청해봤다' 금지.
2. 가격, 날짜, 지원금, 할인율, 자격조건, 판매량 등 검증이 필요한 숫자는 위 스니펫에 명시된 경우에만 사용한다.
3. 스니펫이 불충분하면 숫자 대신 독자가 확인해야 할 항목과 판단 기준을 설명한다.
4. 광고성 결론, 과장, 공포형 낚시, 근거 없는 최상급을 쓰지 않는다.
5. 같은 문장 종결을 연속 3회 이상 반복하지 않는다.
6. '알아보겠습니다/정리해 보았습니다/결론적으로/도움이 되었으면' 같은 AI 상투어 금지.
7. 정보가 불확실하면 단정 대신 '검색 결과 기준', '상품·시점에 따라 달라질 수 있다'처럼 범위를 명확히 한다.

[글 품질]
- 본문 {cmin}~{cmax}자
- 첫 2문단에서 독자의 상황/문제를 바로 제시하고 핵심 키워드를 자연스럽게 1회 사용
- 섹션 3~4개. 소제목은 내용형 문장으로 쓰고 숫자 목차를 기계적으로 반복하지 말 것
- 문단은 모바일에서 읽기 쉽게 1~3문장
- 각 섹션에는 '그래서 독자가 무엇을 보면 되는지'가 있어야 한다
- 결론은 요약 복붙이 아니라 선택 기준 또는 다음 행동 1~2개를 제시
- 제목 후보 5개. 검색 키워드 + 구체적 효용/궁금증을 살리되 거짓 체험형 제목 금지
- 이미지 쿼리 {imin}~{imax}개. 구체적인 사물/장면 중심 검색어

JSON만 출력:
{{"angle":"...","keyword":"...","title_candidates":["..."],"title":"...",
"intro":["..."],"sections":[{{"heading":"...","paragraphs":["..."],"emphasis":"...","centered_lines":[]}}],
"conclusion":["..."],"image_queries":["..."]}}
"""


def _editor_review(post, evidence):
    body = _post_text(post)
    prompt = f"""
다음 글을 네이버 생활정보 편집 기준으로 평가하세요.
제목: {post.get('title','')}
본문:\n{body[:4500]}
참고 스니펫:\n{evidence[:3000] if evidence else '- 없음'}

평가 항목: hook, usefulness, specificity, naturalness, factual_discipline, mobile_readability (각 0~10).
특히 실제로 하지 않은 체험을 꾸몄는지, 근거 없는 숫자/정책/가격을 단정했는지 엄격히 보세요.
JSON만 출력: {{"scores":{{"hook":0,"usefulness":0,"specificity":0,"naturalness":0,"factual_discipline":0,"mobile_readability":0}},"problems":["..."],"fixes":["..."]}}
"""
    return llm.chat_json([
        {"role": "system", "content": "당신은 광고 문구보다 신뢰성과 재방문을 중시하는 냉정한 한국어 콘텐츠 편집자입니다."},
        {"role": "user", "content": prompt},
    ], max_tokens=2200, temperature=0.25)


def _rewrite(post, cfg, plan, evidence, recent, issues, review):
    fixes = (review or {}).get("fixes", [])[:6]
    prompt = _generation_prompt(cfg, plan, evidence, recent)
    prompt += "\n\n[초안]\n" + json.dumps(post, ensure_ascii=False)[:9000]
    prompt += "\n\n[반드시 수정할 문제]\n- " + "\n- ".join(issues + fixes)
    prompt += "\n같은 JSON 스키마로 글 전체를 다시 출력하세요. 문제 없는 장점은 유지하세요."
    return llm.chat_json([
        {"role": "system", "content": "당신은 신뢰도 높은 한국어 블로그 원고를 다듬는 시니어 에디터입니다."},
        {"role": "user", "content": prompt},
    ], max_tokens=8000, temperature=0.68)


def _title_score(title, keyword):
    score = 0
    if 20 <= len(title) <= 36:
        score += 3
    elif 18 <= len(title) <= 40:
        score += 1
    if keyword and keyword in title:
        score += 2
    if any(ch.isdigit() for ch in title):
        score += 1
    if title.endswith("?"):
        score += 1
    if any(re.search(p, title) for p in FAKE_EXPERIENCE_PATTERNS):
        score -= 8
    if any(x in title for x in ("충격", "무조건", "모르면 손해", "대박")):
        score -= 3
    return score


def _normalize(post, cfg, plan):
    candidates = [x.strip() for x in (post.get("title_candidates") or []) if isinstance(x, str) and x.strip()]
    if post.get("title"):
        candidates.append(post["title"].strip())
    keyword = post.get("keyword") or plan.get("keyword") or ""
    if candidates:
        post["title"] = max(dict.fromkeys(candidates), key=lambda t: _title_score(t, keyword))
    post["angle"] = post.get("angle") or plan.get("angle", "")
    post["keyword"] = keyword
    post.setdefault("intro", [])
    post.setdefault("sections", [])
    post.setdefault("conclusion", [])
    post.setdefault("image_queries", [])
    post["image_queries"] = post["image_queries"][:cfg["format"]["image_max"]]
    return post


def generate_post(seed_hint=None):
    cfg = _cfg()
    recent = _recent_titles()
    seed = seed_hint or _choose_seed(cfg, recent)
    evidence = research.collect_naver_evidence(seed)
    plan = _topic_plan(cfg, seed, evidence, recent)
    selected_kw = plan.get("keyword") or seed
    if selected_kw != seed:
        better = research.collect_naver_evidence(selected_kw)
        if better:
            evidence = better

    post = llm.chat_json([
        {"role": "system", "content": "당신은 10년차 한국어 생활정보 블로거입니다. 유용성, 사실 절제, 자연스러운 문체를 우선합니다."},
        {"role": "user", "content": _generation_prompt(cfg, plan, evidence, recent)},
    ], max_tokens=8000, temperature=0.72)
    post = _normalize(post, cfg, plan)

    min_editor_score = float(cfg.get("quality", {}).get("min_editor_score", 8.0))
    max_rewrites = int(cfg.get("quality", {}).get("max_rewrites", 2))
    review = None
    for round_no in range(max_rewrites + 1):
        issues = _deterministic_issues(post, cfg)
        try:
            review = _editor_review(post, evidence)
            scores = review.get("scores", {})
            numeric = [float(v) for v in scores.values() if isinstance(v, (int, float))]
            avg = sum(numeric) / len(numeric) if numeric else 0.0
        except Exception as e:
            print("  편집 평가 실패(규칙 검사만 사용):", str(e)[:90])
            avg = min_editor_score if not issues else 0.0
            review = {"scores": {}, "problems": [], "fixes": []}

        if not issues and avg >= min_editor_score:
            break
        if round_no >= max_rewrites:
            if issues:
                raise RuntimeError("품질 게이트 미통과: " + "; ".join(issues[:5]))
            break
        print(f"  품질 점수 {avg:.1f}/10, 규칙문제 {len(issues)}개 → 재작성 {round_no + 1}/{max_rewrites}")
        post = _rewrite(post, cfg, plan, evidence, recent, issues, review)
        post = _normalize(post, cfg, plan)

    body_chars = len(_post_text(post).replace("\n", ""))
    post["_chars"] = body_chars
    post["_angle"] = {"angle": post.get("angle", ""), "keyword": post.get("keyword", "")}
    post["_quality"] = {
        "editor_scores": (review or {}).get("scores", {}),
        "evidence_lines": len(evidence.splitlines()) if evidence else 0,
        "fabricated_experience_guard": True,
    }
    return post


if __name__ == "__main__":
    print(json.dumps(generate_post(), ensure_ascii=False, indent=2)[:5000])
