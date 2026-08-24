# -*- coding: utf-8 -*-
"""LLM provider chain with optional writer/reviewer model separation.

Priority:
1) OpenCode Go (when OPENCODE_GO_API_KEY is set)
2) custom OpenAI-compatible endpoint
3) OpenRouter
4) local Ollama EXAONE

Secrets must live in .env; never commit API keys.
"""
import json
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OPENCODE_GO_KEY = os.getenv("OPENCODE_GO_API_KEY", "").strip()
OPENCODE_GO_MODEL = os.getenv("OPENCODE_GO_MODEL", "kimi-k3").strip() or "kimi-k3"
OPENCODE_GO_REVIEW_MODEL = os.getenv("OPENCODE_GO_REVIEW_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
OPENCODE_GO_VISION_MODEL = os.getenv("OPENCODE_GO_VISION_MODEL", "deepseek-v4-flash-vision-exp").strip() or "deepseek-v4-flash-vision-exp"
OPENCODE_GO_BASE = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "stealth/ox-alpha").strip() or "stealth/ox-alpha"
OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CUSTOM_URL = os.getenv("LLM_BASE_URL", "").strip()
CUSTOM_MODEL = os.getenv("LLM_MODEL", "").strip()
CUSTOM_KEY = os.getenv("LLM_API_KEY", "").strip()


def _extract_content(payload):
    try:
        return payload["choices"][0]["message"].get("content") or ""
    except Exception:
        return ""


def _go_model(role="write"):
    return OPENCODE_GO_REVIEW_MODEL if role == "review" else OPENCODE_GO_MODEL


def _post_opencode_go(messages, max_tokens, temperature, timeout, model=None):
    r = requests.post(
        f"{OPENCODE_GO_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {OPENCODE_GO_KEY}", "Content-Type": "application/json"},
        json={
            "model": model or OPENCODE_GO_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_content(r.json())


def _post_openrouter(messages, max_tokens, temperature, timeout):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning": {"effort": "low"},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_content(r.json())


def _post_ollama(messages, max_tokens, temperature, timeout):
    r = requests.post(
        f"{OLLAMA}/v1/chat/completions",
        json={"model": "exaone3.5", "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_content(r.json())


def _post_custom(messages, max_tokens, temperature, timeout):
    headers = {"Content-Type": "application/json"}
    if CUSTOM_KEY:
        headers["Authorization"] = f"Bearer {CUSTOM_KEY}"
    r = requests.post(
        f"{CUSTOM_URL.rstrip('/')}/chat/completions",
        headers=headers,
        json={"model": CUSTOM_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_content(r.json())


def engines(role="write"):
    chain = []
    if OPENCODE_GO_KEY:
        model = _go_model(role)
        chain.append((
            f"opencode-go:{model}",
            lambda messages, max_tokens, temperature, timeout, _m=model:
                _post_opencode_go(messages, max_tokens, temperature, timeout, model=_m),
        ))
    if CUSTOM_URL and CUSTOM_MODEL:
        chain.append((f"custom:{CUSTOM_MODEL}", _post_custom))
    if OPENROUTER_KEY:
        chain.append((f"openrouter:{OPENROUTER_MODEL}", _post_openrouter))
    try:
        if requests.get(f"{OLLAMA}/api/tags", timeout=2).status_code == 200:
            chain.append(("ollama:exaone3.5", _post_ollama))
    except Exception:
        pass
    return chain


def chat(messages, max_tokens=4000, temperature=0.8, timeout=300, role="write"):
    errs = []
    chain = engines(role=role)
    if not chain:
        raise RuntimeError("사용 가능한 LLM이 없습니다. .env에 OPENCODE_GO_API_KEY 등을 설정하세요.")
    for name, fn in chain:
        for attempt in range(2):
            try:
                out = fn(messages, max_tokens, temperature, timeout)
                if out and out.strip():
                    return out.strip()
                errs.append(f"{name}:empty")
            except Exception as e:
                errs.append(f"{name}:{str(e)[:120]}")
                if attempt == 0:
                    time.sleep(2)
    raise RuntimeError("모든 LLM 엔진 실패: " + " | ".join(errs))


def _json_candidates(text):
    text = (text or "").strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    yield fenced
    starts = [i for i, ch in enumerate(fenced) if ch in "{["]
    for start in starts[:4]:
        for end in range(len(fenced), start, -1):
            chunk = fenced[start:end].strip()
            if chunk and chunk[-1:] in "}]":
                yield chunk
                break


def _resolve_role(messages, role):
    """Send explicit scoring/fact-check prompts to the independent reviewer model."""
    if role != "write":
        return role
    text = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
    review_markers = (
        "평가 항목:", "0~10", "unsupported_claims", "최근 실제 발행 글을 묶어서 평가",
        "실제 발행된 글을 혹평", "채점합니다",
    )
    if sum(1 for marker in review_markers if marker in text) >= 2:
        return "review"
    return role


def chat_json(messages, max_tokens=6000, temperature=0.7, retries=2, role="write"):
    last = None
    msgs = list(messages)
    effective_role = _resolve_role(msgs, role)
    for _ in range(retries + 1):
        out = chat(msgs, max_tokens=max_tokens, temperature=min(0.7, temperature), role=effective_role)
        parsed = None
        for candidate in _json_candidates(out):
            try:
                parsed = json.loads(candidate)
                break
            except Exception as e:
                last = e
        if parsed is not None:
            return parsed
        msgs += [
            {"role": "assistant", "content": out[:2500]},
            {"role": "user", "content": "위 출력은 JSON 파싱에 실패했습니다. 설명/코드펜스 없이 유효한 JSON만 다시 출력하세요."},
        ]
    raise RuntimeError(f"JSON 파싱 실패: {last}")


def vision(image_b64_url, prompt, max_tokens=800, temperature=0.2, timeout=90):
    """Vision relevance check using OpenCode Go first, then OpenRouter."""
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_b64_url}},
        {"type": "text", "text": prompt},
    ]}]
    if OPENCODE_GO_KEY:
        r = requests.post(
            f"{OPENCODE_GO_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {OPENCODE_GO_KEY}", "Content-Type": "application/json"},
            json={"model": OPENCODE_GO_VISION_MODEL, "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=timeout,
        )
        r.raise_for_status()
        return _extract_content(r.json()).strip()
    if OPENROUTER_KEY:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_MODEL, "max_tokens": max_tokens,
                  "temperature": temperature, "messages": messages},
            timeout=timeout,
        )
        r.raise_for_status()
        return _extract_content(r.json()).strip()
    raise RuntimeError("비전 검증에 사용할 API 키가 없습니다")


if __name__ == "__main__":
    print("writer engines:", [n for n, _ in engines("write")])
    print("review engines:", [n for n, _ in engines("review")])
