# -*- coding: utf-8 -*-
"""Evidence-ranked, feedback-aware, quality-gated blog writer."""
import json
import os
import random
import re
from collections import Counter

import llm
import quality_feedback
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
TITLE_STOP = {
    "이렇게", "하는", "방법", "이유", "정리", "알뜰", "절약", "생활", "정보", "체크",
    "상품", "구매", "가격", "사용", "후기", "기준", "지금", "확인", "하면", "되는",
}
FACT_NUMBER_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:만원|천원|원대|원|%|퍼센트|개월|년|일|GB|기가|kg|g|명)"
)


def _cfg():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def _recent_records(n=100):
    path = os.path.join(BASE, "logs", "published.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out[-n:]


def _recent_titles(n=80):
    return [x.get("title", "") for x in _recent_records(n) if x.get("title")][-n:]


def _post_text(post):
    bits = list(post.get("intro", []))
    for sec in post.get("sections", []):
        bits.append(sec.get("heading", ""))
        bits.extend(sec.get("paragraphs", []))
        if sec.get("emphasis"):
            bits.append(sec["emphasis"])
        bits.extend(sec.get("centered_lines") or [])
    bits.extend(post.get("conclusion", []))
    return "\n".join(x for x in bits if isinstance(x, str) and x)


def _title_tokens(text):
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
    return {w for w in words if w not in TITLE_STOP and not w.isdigit()}


def _title_similarity(a, b):
    aa, bb = _title_tokens(a), _title_tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _max_recent_similarity(title, recent):
    return max((_title_similarity(title, x) for x in recent if x), default=0.0)


def _norm_number_token(token):
    return re.sub(r"\s+", "", (token or "").replace(",", "")).lower()


def _unsupported_number_claims(post, evidence_bundle):
    joined = post.get("title", "") + "\n" + _post_text(post)
    claims = list(dict.fromkeys(FACT_NUMBER_RE.findall(joined)))
    if not claims:
        return []
    evidence = _norm_number_token(research.evidence_text(evidence_bundle))
    return [c for c in claims if _norm_number_token(c) not in evidence]


def _deterministic_issues(post, cfg, evidence_bundle, recent):
    issues = []
    title = post.get("title", "")
    body = _post_text(post)
    quality = cfg.get("quality", {})
    tmin = int(cfg.get("format", {}).get("title_min", 20))
    tmax = int(cfg.get("format", {}).get("title_max", 36))
    if not tmin - 2 <= len(title) <= tmax + 4:
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

    chars = len(body.replace("\n", ""))
    cmin = int(cfg["format"]["char_min"])
    cmax = int(cfg["format"]["char_max"])
    if chars < cmin * 0.88:
        issues.append("본문이 너무 짧음")
    if chars > cmax * 1.20:
        issues.append("본문이 너무 김")

    headings = [s.get("heading", "") for s in post.get("sections", []) if s.get("heading")]
    if len(headings) < 3:
        issues.append("섹션 부족")
    if any(len(h) < 6 or len(h) > 42 for h in headings):
        issues.append("소제목 길이/정보량 불균형")

    endings = re.findall(r"(습니다|는데요|더라고요|입니다|했어요|됩니다)[.!?]?", body)
    if endings:
        top = Counter(endings).most_common(1)[0][1]
        if top / len(endings) > 0.58 and len(endings) >= 8:
            issues.append("문장 종결 패턴 반복")

    similarity = _max_recent_similarity(title, recent[-40:])
    max_sim = float(quality.get("max_recent_title_similarity", 0.72))
    if similarity >= max_sim:
        issues.append(f"최근 제목과 소재/표현 중복({similarity:.0%})")

    unsupported = _unsupported_number_claims(post, evidence_bundle)
    if unsupported:
        issues.append("검색 근거에 없는 숫자 주장: " + ", ".join(unsupported[:4]))

    if evidence_bundle.get("high_stakes"):
        min_official = int(quality.get("min_official_sources_high_stakes", 1))
        if evidence_bundle.get("official_count", 0) < min_official and FACT_NUMBER_RE.search(title + "\n" + body):
            issues.append("정책/금전성 주제인데 공식출처 없이 구체 숫자를 단정함")

    return list(dict.fromkeys(issues))


def _choose_seed(cfg, recent, feedback):
    keywords = list(cfg["topic"].get("keywords", []))
    random.shuffle(keywords)
    recent_text = " ".join(recent[-30:])
    avoid = set(feedback.get("avoid_angle_tokens", []))
    fresh = [k for k in keywords if k not in recent_text and not any(a in k for a in avoid)]
    return (fresh or keywords or [cfg["topic"]["name"]])[0]


def _choose_content_mode(cfg):
    modes = cfg.get("topic", {}).get("content_modes") or [
        "비교·선택 기준", "실수 방지", "구매 전 체크", "변경사항 해설", "절약 체크리스트", "조건 확인 가이드"
    ]
    return random.choice(modes)


def _topic_plan(cfg, seed, evidence_bundle, recent, feedback, content_mode):
    evidence = research.format_evidence(evidence_bundle)
    feedback_text = quality_feedback.format_generation_feedback(feedback)
    strength = f"공식출처 {evidence_bundle.get('official_count', 0)}개 / 총 {len(evidence_bundle.get('items', []))}개"
    prompt = f"""
블로그 주제: {cfg['topic']['name']}
주제 설명: {cfg['topic'].get('description','')}
시드 키워드: {seed}
이번 글의 콘텐츠 모드: {content_mode}
최근 제목(중복 피하기): {json.dumps(recent[-25:], ensure_ascii=False)}
근거 강도: {strength}
고위험 정책/금전 주제 여부: {evidence_bundle.get('high_stakes', False)}

[누적 품질 피드백]
{feedback_text}

[검색 근거 - T1이 가장 강하고 T5는 보조 참고]
{evidence}

오늘 쓸 소재 후보 5개를 만든 뒤 가장 좋은 1개를 고르세요.
- 최근 제목과 사건/효용/질문이 겹치지 않을 것
- 지정된 콘텐츠 모드의 독자 효용을 살릴 것
- 생활자가 실제로 궁금해할 구체적인 문제를 해결할 것
- T1/T2 근거를 우선하고 T4/T5만으로 정책·가격·자격을 단정하지 말 것
- 검색 근거에 없는 가격, 날짜, 통계, 혜택 수치를 지어내지 말 것
- 실제 사용하지 않았는데 '3개월 써봤다', '직접 신청했다', '내돈내산' 같은 체험을 만들지 말 것
- 고위험 주제인데 공식출처가 없다면 금액/자격 단정 대신 확인 경로·준비사항·판단 기준 중심 소재를 고를 것

JSON만 출력:
{{"candidates":[{{"angle":"...","keyword":"...","reader_need":"..."}}],
 "selected":{{"angle":"...","keyword":"...","reader_need":"..."}}}}
"""
    try:
        data = llm.chat_json([
            {"role": "system", "content": "당신은 네이버 생활정보 콘텐츠 편집장입니다. 정확성, 새로움, 독자 효용을 우선합니다."},
            {"role": "user", "content": prompt},
        ], max_tokens=2600, temperature=0.62)
        return data.get("selected") or (data.get("candidates") or [{}])[0]
    except Exception as e:
        print("  소재 계획 실패 → 기본 시드 사용:", str(e)[:90])
        return {"angle": f"{seed}에서 놓치기 쉬운 선택 기준", "keyword": seed, "reader_need": "실용 정보"}


def _generation_prompt(cfg, plan, evidence_bundle, recent, feedback, content_mode):
    cmin, cmax = cfg["format"]["char_min"], cfg["format"]["char_max"]
    imin, imax = cfg["format"]["image_min"], cfg["format"]["image_max"]
    evidence = research.format_evidence(evidence_bundle)
    feedback_text = quality_feedback.format_generation_feedback(feedback)
    return f"""
[콘텐츠 브리프]
주제: {cfg['topic']['name']}
콘텐츠 모드: {content_mode}
핵심 소재: {plan.get('angle','')}
핵심 키워드: {plan.get('keyword','')}
독자 니즈: {plan.get('reader_need','')}
최근 제목: {json.dumps(recent[-20:], ensure_ascii=False)}

[누적 품질 피드백 - 이번 글에서 실제로 개선]
{feedback_text}

[검색 근거 - T1 공식 > T2 기관/웹 > T3 뉴스 > T4 커머스 > T5 UGC]
{evidence}

[절대 규칙]
1. 실제로 하지 않은 경험을 만들지 않는다. '직접 써봤다/3개월 사용/내돈내산/신청해봤다' 금지.
2. 가격, 날짜, 지원금, 할인율, 자격조건, 판매량 등 검증이 필요한 숫자는 위 근거에 같은 수치가 명시된 경우에만 사용한다.
3. T4/T5만 있는 주장은 사실 확정 근거로 쓰지 않는다. 특히 정책·지원금·자격은 T1을 최우선한다.
4. 공식출처가 없는 고위험 주제는 금액/자격을 단정하지 말고 '무엇을 어디서 확인할지'를 알려준다.
5. 광고성 결론, 과장, 공포형 낚시, 근거 없는 최상급을 쓰지 않는다.
6. 같은 문장 종결을 연속 3회 이상 반복하지 않는다.
7. '알아보겠습니다/정리해 보았습니다/결론적으로/도움이 되었으면' 같은 AI 상투어 금지.
8. 정보가 불확실하면 단정 대신 출처 범위와 시점에 따라 달라질 수 있음을 자연스럽게 표시한다.
9. 최근 제목을 단어만 바꿔 재활용하지 않는다. 같은 사건이면 독자 문제와 결론이 달라야 한다.

[글 품질]
- 본문 {cmin}~{cmax}자
- 첫 2문단에서 독자의 상황/문제를 바로 제시하고 핵심 키워드를 자연스럽게 1회 사용
- 섹션 3~4개. 소제목은 8~32자 정도의 내용형 문장으로 쓰고 '1. 2. 3.' 기계적 목차를 쓰지 말 것
- 문단은 모바일에서 읽기 쉽게 1~3문장
- 각 섹션에는 독자가 실제로 비교·확인·행동할 포인트가 있어야 한다
- 결론은 본문 복붙 요약이 아니라 선택 기준 또는 다음 행동 1~2개를 제시
- 제목 후보 5개. 검색 키워드 + 구체적 효용/궁금증을 살리되 거짓 체험형 제목 금지
- 숫자를 제목 장식용으로 만들지 말 것. 근거에 있는 수치만 사용
- 이미지 쿼리 {imin}~{imax}개. 구체적인 사물/장면 중심 검색어

검증 가능한 숫자·정책 주장을 썼다면 fact_claims에 최대 6개를 기록한다. 근거 문구가 없는 주장은 fact_claims에도 본문에도 쓰지 않는다.
JSON만 출력:
{{"angle":"...","keyword":"...","title_candidates":["..."],"title":"...",
"intro":["..."],"sections":[{{"heading":"...","paragraphs":["..."],"emphasis":"...","centered_lines":[]}}],
"conclusion":["..."],"image_queries":["..."],
"fact_claims":[{{"claim":"...","evidence_domain":"...","evidence_text":"..."}}]}}
"""


def _editor_review(post, evidence_bundle):
    body = _post_text(post)
    evidence = research.format_evidence(evidence_bundle, max_chars=4500)
    prompt = f"""
다음 글을 네이버 생활정보 편집 기준으로 평가하세요.
제목: {post.get('title','')}
본문:\n{body[:4800]}
검색 근거:\n{evidence}

평가 항목: hook, usefulness, specificity, naturalness, factual_discipline, mobile_readability (각 0~10).
실제로 하지 않은 체험, 근거 없는 숫자/정책/가격, T4/T5만으로 단정한 중요 주장을 특히 엄격히 보세요.
본문의 검증 가능한 주장 중 검색 근거에서 뒷받침되지 않는 문장은 unsupported_claims에 짧게 적으세요.
JSON만 출력: {{"scores":{{"hook":0,"usefulness":0,"specificity":0,"naturalness":0,"factual_discipline":0,"mobile_readability":0}},"unsupported_claims":["..."],"problems":["..."],"fixes":["..."]}}
"""
    return llm.chat_json([
        {"role": "system", "content": "당신은 광고 문구보다 신뢰성과 재방문을 중시하는 냉정한 한국어 콘텐츠 편집자입니다."},
        {"role": "user", "content": prompt},
    ], max_tokens=2600, temperature=0.2)


def _rewrite(post, cfg, plan, evidence_bundle, recent, feedback, content_mode, issues, review):
    fixes = (review or {}).get("fixes", [])[:6]
    prompt = _generation_prompt(cfg, plan, evidence_bundle, recent, feedback, content_mode)
    prompt += "\n\n[초안]\n" + json.dumps(post, ensure_ascii=False)[:9000]
    prompt += "\n\n[반드시 수정할 문제]\n- " + "\n- ".join(issues + fixes)
    prompt += "\n같은 JSON 스키마로 글 전체를 다시 출력하세요. 문제 없는 장점은 유지하세요."
    return llm.chat_json([
        {"role": "system", "content": "당신은 신뢰도 높은 한국어 블로그 원고를 다듬는 시니어 에디터입니다."},
        {"role": "user", "content": prompt},
    ], max_tokens=8000, temperature=0.64)


def _title_score(title, keyword, evidence_bundle):
    score = 0
    if 20 <= len(title) <= 36:
        score += 3
    elif 18 <= len(title) <= 40:
        score += 1
    if keyword and keyword in title:
        score += 2
    if title.endswith("?"):
        score += 1
    if any(x in title for x in ("기준", "차이", "전", "왜", "언제", "확인")):
        score += 1
    if any(re.search(p, title) for p in FAKE_EXPERIENCE_PATTERNS):
        score -= 10
    if any(x in title for x in ("충격", "무조건", "모르면 손해", "대박")):
        score -= 4
    numbers = FACT_NUMBER_RE.findall(title)
    if numbers:
        ev = _norm_number_token(research.evidence_text(evidence_bundle))
        if all(_norm_number_token(n) in ev for n in numbers):
            score += 1
        else:
            score -= 6
    return score


def _normalize(post, cfg, plan, evidence_bundle):
    candidates = [x.strip() for x in (post.get("title_candidates") or []) if isinstance(x, str) and x.strip()]
    if post.get("title"):
        candidates.append(post["title"].strip())
    keyword = post.get("keyword") or plan.get("keyword") or ""
    if candidates:
        post["title"] = max(dict.fromkeys(candidates), key=lambda t: _title_score(t, keyword, evidence_bundle))
    post["angle"] = post.get("angle") or plan.get("angle", "")
    post["keyword"] = keyword
    post.setdefault("intro", [])
    post.setdefault("sections", [])
    post.setdefault("conclusion", [])
    post.setdefault("image_queries", [])
    post.setdefault("fact_claims", [])
    post["image_queries"] = post["image_queries"][:cfg["format"]["image_max"]]
    clean_sections = []
    for sec in post.get("sections", [])[:4]:
        if not isinstance(sec, dict):
            continue
        sec["heading"] = re.sub(r"^\s*\d+\s*[.)-]\s*", "", str(sec.get("heading", ""))).strip()
        sec.setdefault("paragraphs", [])
        sec.setdefault("emphasis", "")
        sec.setdefault("centered_lines", [])
        if sec["heading"] and sec["paragraphs"]:
            clean_sections.append(sec)
    post["sections"] = clean_sections
    return post


def generate_post(seed_hint=None):
    cfg = _cfg()
    recent = _recent_titles()
    feedback = quality_feedback.build_generation_feedback()
    seed = seed_hint or _choose_seed(cfg, recent, feedback)
    content_mode = _choose_content_mode(cfg)

    evidence_bundle = research.collect_evidence(
        seed,
        max_items=int(cfg.get("research", {}).get("max_sources", 12)),
        official_search=bool(cfg.get("research", {}).get("official_search_for_high_stakes", True)),
    )
    plan = _topic_plan(cfg, seed, evidence_bundle, recent, feedback, content_mode)
    selected_kw = plan.get("keyword") or seed
    if selected_kw != seed:
        better = research.collect_evidence(
            selected_kw,
            max_items=int(cfg.get("research", {}).get("max_sources", 12)),
            official_search=bool(cfg.get("research", {}).get("official_search_for_high_stakes", True)),
        )
        if better.get("items"):
            evidence_bundle = better

    post = llm.chat_json([
        {"role": "system", "content": "당신은 10년차 한국어 생활정보 블로거입니다. 유용성, 사실 절제, 자연스러운 문체를 우선합니다."},
        {"role": "user", "content": _generation_prompt(cfg, plan, evidence_bundle, recent, feedback, content_mode)},
    ], max_tokens=8000, temperature=0.68)
    post = _normalize(post, cfg, plan, evidence_bundle)

    min_editor_score = float(cfg.get("quality", {}).get("min_editor_score", 8.2))
    max_rewrites = int(cfg.get("quality", {}).get("max_rewrites", 2))
    review = None
    final_issues = []
    avg = 0.0
    for round_no in range(max_rewrites + 1):
        issues = _deterministic_issues(post, cfg, evidence_bundle, recent)
        try:
            review = _editor_review(post, evidence_bundle)
            scores = review.get("scores", {})
            numeric = [float(v) for v in scores.values() if isinstance(v, (int, float))]
            avg = sum(numeric) / len(numeric) if numeric else 0.0
            unsupported = [str(x) for x in (review.get("unsupported_claims") or []) if str(x).strip()]
            if unsupported:
                issues.append("편집자 검증에서 근거 부족 주장: " + " / ".join(unsupported[:3]))
        except Exception as e:
            print("  편집 평가 실패(규칙 검사만 사용):", str(e)[:90])
            avg = min_editor_score if not issues else 0.0
            review = {"scores": {}, "unsupported_claims": [], "problems": [], "fixes": []}

        issues = list(dict.fromkeys(issues))
        final_issues = issues
        if not issues and avg >= min_editor_score:
            break
        if round_no >= max_rewrites:
            if issues:
                raise RuntimeError("품질 게이트 미통과: " + "; ".join(issues[:5]))
            break
        print(f"  품질 점수 {avg:.1f}/10, 규칙문제 {len(issues)}개 → 재작성 {round_no + 1}/{max_rewrites}")
        post = _rewrite(post, cfg, plan, evidence_bundle, recent, feedback, content_mode, issues, review)
        post = _normalize(post, cfg, plan, evidence_bundle)

    body_chars = len(_post_text(post).replace("\n", ""))
    post["_chars"] = body_chars
    post["_angle"] = {"angle": post.get("angle", ""), "keyword": post.get("keyword", "")}
    post["_sources"] = research.evidence_sources(evidence_bundle)
    post["_quality"] = {
        "editor_scores": (review or {}).get("scores", {}),
        "editor_average": round(avg, 2),
        "evidence_sources": len(evidence_bundle.get("items", [])),
        "official_sources": evidence_bundle.get("official_count", 0),
        "high_stakes": evidence_bundle.get("high_stakes", False),
        "fabricated_experience_guard": True,
        "unsupported_number_guard": True,
        "recent_similarity": round(_max_recent_similarity(post.get("title", ""), recent[-40:]), 3),
        "feedback_weak_dimensions": feedback.get("weak_dimensions", []),
        "content_mode": content_mode,
        "fact_claims": len(post.get("fact_claims", [])),
        "final_issues": final_issues,
    }
    return post


if __name__ == "__main__":
    print(json.dumps(generate_post(), ensure_ascii=False, indent=2)[:6000])
