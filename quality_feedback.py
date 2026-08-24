# -*- coding: utf-8 -*-
"""Closed-loop quality feedback from recent generated and live blog posts."""
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(BASE, "logs")
PUBLISH_LOG = os.path.join(LOGDIR, "published.jsonl")
LIVE_FEEDBACK = os.path.join(LOGDIR, "live_feedback.json")
KST = ZoneInfo("Asia/Seoul")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

DIMENSION_FIXES = {
    "hook": "첫 2문단에서 독자가 겪는 상황과 얻을 이익을 더 빨리 제시한다.",
    "usefulness": "각 섹션마다 독자가 바로 적용할 선택 기준이나 다음 행동을 넣는다.",
    "specificity": "근거 안에서 제품명·조건·상황을 구체화하고 추상적인 조언을 줄인다.",
    "naturalness": "같은 어미와 문장 길이 반복을 줄이고 설명문·짧은 문장을 섞는다.",
    "factual_discipline": "검색 근거에 없는 숫자·기간·정책 조건은 삭제하거나 확인 항목으로 바꾼다.",
    "mobile_readability": "한 문단을 1~3문장으로 유지하고 긴 문장을 둘로 나눈다.",
}
STOP_TOKENS = {
    "이렇게", "하는", "방법", "이유", "정리", "알뜰", "절약", "생활", "정보", "체크",
    "상품", "구매", "가격", "사용", "후기", "기준", "지금", "확인",
}


def _tokens(text):
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
    return [w for w in words if w not in STOP_TOKENS and not w.isdigit()]


def _iter_publish_log(limit=60):
    if not os.path.exists(PUBLISH_LOG):
        return []
    out = []
    try:
        with open(PUBLISH_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-limit:]


def _score_dict(rec):
    q = rec.get("quality") or {}
    if not isinstance(q, dict):
        return {}
    if isinstance(q.get("editor_scores"), dict):
        return q["editor_scores"]
    return {k: v for k, v in q.items() if isinstance(v, (int, float))}


def _load_live_feedback(max_age_days=7):
    if not os.path.exists(LIVE_FEEDBACK):
        return {}
    try:
        data = json.load(open(LIVE_FEEDBACK, encoding="utf-8"))
        ts = datetime.fromisoformat(data.get("generated_at", ""))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        if datetime.now(KST) - ts > timedelta(days=max_age_days):
            return {}
        return data
    except Exception:
        return {}


def build_generation_feedback():
    """Build deterministic instructions from recent quality scores and angles."""
    records = _iter_publish_log(50)
    buckets = defaultdict(list)
    angle_tokens = Counter()
    recent_titles = []
    for rec in records:
        title = rec.get("title")
        if title:
            recent_titles.append(title)
        for key, val in _score_dict(rec).items():
            if isinstance(val, (int, float)):
                buckets[key].append(float(val))
        angle_tokens.update(_tokens(rec.get("angle", "")))

    live = _load_live_feedback()
    for key, val in (live.get("aggregate_scores") or {}).items():
        if isinstance(val, (int, float)):
            buckets[key].append(float(val))

    averages = {k: round(sum(v) / len(v), 2) for k, v in buckets.items() if v}
    weak = [k for k, v in sorted(averages.items(), key=lambda kv: kv[1]) if v < 8.3][:3]
    instructions = [DIMENSION_FIXES[k] for k in weak if k in DIMENSION_FIXES]
    instructions.extend((live.get("instructions") or [])[:3])
    # Preserve order while removing duplicates.
    instructions = list(dict.fromkeys(x for x in instructions if x))[:6]
    avoid_angles = [w for w, n in angle_tokens.most_common(8) if n >= 2][:6]

    return {
        "aggregate_scores": averages,
        "weak_dimensions": weak,
        "instructions": instructions,
        "avoid_angle_tokens": avoid_angles,
        "recent_titles": recent_titles[-30:],
        "live_feedback_available": bool(live),
    }


def format_generation_feedback(feedback):
    if not feedback:
        return "- 누적 품질 피드백 없음"
    lines = []
    if feedback.get("weak_dimensions"):
        lines.append("약한 품질 항목: " + ", ".join(feedback["weak_dimensions"]))
    if feedback.get("avoid_angle_tokens"):
        lines.append("최근 반복 소재 토큰(가급적 피하기): " + ", ".join(feedback["avoid_angle_tokens"]))
    for ins in feedback.get("instructions", []):
        lines.append("개선 지시: " + ins)
    return "\n".join("- " + x for x in lines) or "- 누적 품질 피드백 없음"


def _rss_posts(blog_id, limit=5):
    r = requests.get(f"https://rss.blog.naver.com/{blog_id}.xml", headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    rss = r.text
    items = re.findall(r"<item>(.*?)</item>", rss, re.S)
    out = []
    for item in items[:limit]:
        title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item, re.S)
        link = re.search(r"<link><!\[CDATA\[(.*?)\]\]></link>", item, re.S) or re.search(r"<link>(.*?)</link>", item, re.S)
        if title and link:
            out.append({"title": re.sub(r"\s+", " ", title.group(1)).strip(), "url": link.group(1).strip()})
    return out


def _fetch_post_body(blog_id, url):
    m = re.search(r"logNo=(\d+)", url) or re.search(rf"/{re.escape(blog_id)}/(\d+)", url)
    if not m:
        return ""
    post_url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={m.group(1)}"
    r = requests.get(post_url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    html = r.text
    body_m = re.search(r'class="se-main-container"(.*?)</article>', html, re.S)
    segment = body_m.group(1) if body_m else html
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", segment, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;|&#xA0;", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def refresh_live_feedback(blog_id, limit=4):
    """Re-read recent live posts, score them in one LLM batch, and persist next-run lessons."""
    os.makedirs(LOGDIR, exist_ok=True)
    posts = []
    try:
        for item in _rss_posts(blog_id, limit=limit):
            try:
                body = _fetch_post_body(blog_id, item["url"])
            except Exception as e:
                print("  라이브 본문 수집 실패:", str(e)[:80])
                body = ""
            if len(body) >= 250:
                posts.append({"title": item["title"], "body": body[:3200], "url": item["url"]})
    except Exception as e:
        raise RuntimeError("RSS 품질 피드백 수집 실패: " + str(e)[:120])

    if not posts:
        raise RuntimeError("평가할 최근 라이브 글을 찾지 못했습니다")

    import llm
    payload = [{"title": p["title"], "body": p["body"]} for p in posts]
    review = llm.chat_json([
        {"role": "system", "content": "당신은 장기 신뢰도와 재방문을 중시하는 네이버 생활정보 콘텐츠 편집장입니다."},
        {"role": "user", "content":
            "최근 실제 발행 글을 묶어서 평가하세요. 광고성, 허위 체험, 반복되는 제목 패턴, 추상적 문장, 모바일 가독성을 엄격히 봅니다.\n"
            "각 글은 hook,usefulness,specificity,naturalness,factual_discipline,mobile_readability를 0~10으로 채점합니다.\n"
            "JSON만: {\"posts\":[{\"title\":\"...\",\"scores\":{...},\"problems\":[\"...\"]}],"
            "\"global_problems\":[\"...\"],\"instructions\":[\"다음 글에 적용할 구체 지시\"]}\n\n"
            + json.dumps(payload, ensure_ascii=False)[:13000]},
    ], max_tokens=5000, temperature=0.2)

    score_buckets = defaultdict(list)
    reviewed = review.get("posts") or []
    for p in reviewed:
        for k, v in (p.get("scores") or {}).items():
            if isinstance(v, (int, float)):
                score_buckets[k].append(float(v))
    aggregate = {k: round(sum(v) / len(v), 2) for k, v in score_buckets.items() if v}
    data = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "blog_id": blog_id,
        "post_count": len(posts),
        "aggregate_scores": aggregate,
        "global_problems": (review.get("global_problems") or [])[:8],
        "instructions": (review.get("instructions") or [])[:8],
        "titles": [p["title"] for p in posts],
    }
    with open(LIVE_FEEDBACK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
