# -*- coding: utf-8 -*-
"""Resilient LLM provider chain for blog generation.

Priority:
1) OpenCode Go DeepSeek V4 Flash (when OPENCODE_GO_API_KEY is set)
2) custom OpenAI-compatible endpoint
3) OpenRouter
4) local Ollama, only when the configured model actually exists

OpenCode Go has a hard cost ceiling: no request may select a model other than
DeepSeek V4 Flash. Secrets must live in .env; never commit API keys.
"""
import json
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OPENCODE_GO_KEY = os.getenv("OPENCODE_GO_API_KEY", "").strip()
OPENCODE_GO_PINNED_MODEL = "deepseek-v4-flash"
# Keep the public names for compatibility with existing callers/diagnostics, but
# intentionally ignore model/fallback environment overrides for OpenCode Go.
OPENCODE_GO_MODEL = OPENCODE_GO_PINNED_MODEL
OPENCODE_GO_REVIEW_MODEL = OPENCODE_GO_PINNED_MODEL
OPENCODE_GO_VISION_MODEL = OPENCODE_GO_PINNED_MODEL
OPENCODE_GO_BASE = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")
OPENCODE_GO_FALLBACK_MODELS = OPENCODE_GO_PINNED_MODEL
OPENCODE_GO_REVIEW_FALLBACK_MODELS = OPENCODE_GO_PINNED_MODEL
OPENCODE_GO_SEND_TEMPERATURE = os.getenv("OPENCODE_GO_SEND_TEMPERATURE", "0") == "1"
OPENCODE_GO_MAX_OUTPUT = max(256, int(os.getenv("OPENCODE_GO_MAX_OUTPUT", "6000")))

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "stealth/ox-alpha").strip() or "stealth/ox-alpha"
OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5").strip() or "exaone3.5"
CUSTOM_URL = os.getenv("LLM_BASE_URL", "").strip()
CUSTOM_MODEL = os.getenv("LLM_MODEL", "").strip()
CUSTOM_KEY = os.getenv("LLM_API_KEY", "").strip()


def _extract_content(payload):
    """Extract plain assistant text from an OpenAI-compatible response."""
    try:
        content = payload["choices"][0]["message"].get("content")
    except Exception:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    out.append(text)
        return "\n".join(out)
    return ""


def _model_list(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _go_candidates(role="write"):
    """Return the only OpenCode Go model allowed by the cost policy."""
    del role
    return [OPENCODE_GO_PINNED_MODEL]


def _short_error_response(response, limit=480):
    try:
        text = response.text or ""
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or response.reason or "unknown error"


def _post_opencode_go(messages, max_tokens, temperature, timeout, model=None):
    """Use a minimal Chat Completions payload pinned to DeepSeek V4 Flash.

    The ``model`` argument remains for backwards compatibility but is intentionally
    ignored. Some OpenCode Go upstreams are strict about optional fields, so
    temperature is omitted by default and can be re-enabled separately.
    """
    requested_model = (model or OPENCODE_GO_PINNED_MODEL).strip()
    if requested_model != OPENCODE_GO_PINNED_MODEL:
        raise RuntimeError(
            f"OpenCode Go model blocked by cost policy: {requested_model or '<empty>'}; "
            f"allowed={OPENCODE_GO_PINNED_MODEL}"
        )
    chosen = requested_model
    payload = {
        "model": chosen,
        "messages": messages,
        "stream": False,
        "max_tokens": min(max(64, int(max_tokens)), OPENCODE_GO_MAX_OUTPUT),
    }
    if OPENCODE_GO_SEND_TEMPERATURE:
        payload["temperature"] = temperature

    if payload.get("model") != OPENCODE_GO_PINNED_MODEL:
        raise RuntimeError("OpenCode Go request blocked immediately before HTTP dispatch")

    if payload.get("model") != OPENCODE_GO_PINNED_MODEL:
        raise RuntimeError("OpenCode Go request blocked immediately before HTTP dispatch")

    r = requests.post(
        f"{OPENCODE_GO_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENCODE_GO_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(
            f"HTTP {r.status_code} model={chosen}: {_short_error_response(r)}"
        )
    out = _extract_content(r.json())
    if not out.strip():
        raise RuntimeError(f"HTTP {r.status_code} model={chosen}: empty assistant content")
    return out


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
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} ollama:{OLLAMA_MODEL}: {_short_error_response(r)}")
    return _extract_content(r.json())


def _post_custom(messages, max_tokens, temperature, timeout):
    headers = {"Content-Type": "application/json"}
    if CUSTOM_KEY:
        headers["Authorization"] = f"Bearer {CUSTOM_KEY}"
    r = requests.post(
        f"{CUSTOM_URL.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": CUSTOM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_content(r.json())


def _ollama_model_available():
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=2)
        if r.status_code != 200:
            return False
        rows = r.json().get("models", [])
        names = [str(x.get("name", "")) for x in rows if isinstance(x, dict)]
        return any(n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL + ":") for n in names)
    except Exception:
        return False


def engines(role="write"):
    chain = []
    if OPENCODE_GO_KEY:
        for model in _go_candidates(role):
            chain.append((
                f"opencode-go:{model}",
                lambda messages, max_tokens, temperature, timeout, _m=model:
                    _post_opencode_go(messages, max_tokens, temperature, timeout, model=_m),
            ))
    if CUSTOM_URL and CUSTOM_MODEL:
        chain.append((f"custom:{CUSTOM_MODEL}", _post_custom))
    if OPENROUTER_KEY:
        chain.append((f"openrouter:{OPENROUTER_MODEL}", _post_openrouter))
    if _ollama_model_available():
        chain.append((f"ollama:{OLLAMA_MODEL}", _post_ollama))
    return chain


def chat(messages, max_tokens=4000, temperature=0.8, timeout=300, role="write"):
    errs = []
    chain = engines(role=role)
    if not chain:
        raise RuntimeError("사용 가능한 LLM이 없습니다. .env에 OPENCODE_GO_API_KEY 등을 설정하세요.")

    for name, fn in chain:
        attempts = 1 if name.startswith("opencode-go:") else 2
        for attempt in range(attempts):
            try:
                out = fn(messages, max_tokens, temperature, timeout)
                if out and out.strip():
                    if errs and name.startswith("opencode-go:"):
                        print(f"  LLM 폴백 성공 → {name}")
                    return out.strip()
                errs.append(f"{name}:empty")
            except Exception as e:
                msg = str(e).replace(OPENCODE_GO_KEY, "[REDACTED]") if OPENCODE_GO_KEY else str(e)
                errs.append(f"{name}:{msg[:520]}")
                if attempt + 1 < attempts:
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


def _coerce_single_json_object(value):
    """Normalize a model response that should be one JSON object.

    Some chat models occasionally wrap an otherwise valid object in a one-element array,
    e.g. [{...}]. That shape is safe to recover. Ambiguous arrays or scalar JSON are
    rejected so callers never crash later with a misleading `.get()` AttributeError.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], dict):
            return value[0]
        raise ValueError(
            f"JSON 객체 1개가 필요하지만 배열 {len(value)}개를 받았습니다"
        )
    raise ValueError(
        f"JSON 객체가 필요하지만 {type(value).__name__} 형식을 받았습니다"
    )


def _resolve_role(messages, role):
    """Send explicit scoring/fact-check prompts to the review role."""
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
    """Request and parse one JSON object, repairing common model formatting drift."""
    last = None
    msgs = list(messages)
    effective_role = _resolve_role(msgs, role)
    for _ in range(retries + 1):
        out = chat(
            msgs,
            max_tokens=max_tokens,
            temperature=min(0.7, temperature),
            role=effective_role,
        )
        parsed = None
        for candidate in _json_candidates(out):
            try:
                parsed = _coerce_single_json_object(json.loads(candidate))
                break
            except Exception as e:
                last = e
                parsed = None
        if parsed is not None:
            return parsed
        msgs += [
            {"role": "assistant", "content": out[:2500]},
            {
                "role": "user",
                "content": (
                    "위 출력은 요구한 JSON 객체 형식이 아닙니다. "
                    "배열로 감싸지 말고 설명/코드펜스 없이 JSON 객체 하나만 다시 출력하세요."
                ),
            },
        ]
    raise RuntimeError(f"JSON 객체 파싱 실패: {last}")


def vision(image_b64_url, prompt, max_tokens=800, temperature=0.2, timeout=90):
    """Vision relevance check using Flash-only OpenCode Go first, then OpenRouter."""
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_b64_url}},
        {"type": "text", "text": prompt},
    ]}]
    if OPENCODE_GO_KEY:
        try:
            return _post_opencode_go(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                model=OPENCODE_GO_PINNED_MODEL,
            ).strip()
        except Exception as e:
            if not OPENROUTER_KEY:
                raise
            print("  OpenCode Go 비전 실패 → OpenRouter 폴백:", str(e)[:180])
    if OPENROUTER_KEY:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENROUTER_MODEL,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return _extract_content(r.json()).strip()
    raise RuntimeError("비전 검증에 사용할 API 키가 없습니다")


def probe_go():
    """Cheap connectivity probe for the Flash-only OpenCode Go pool."""
    if not OPENCODE_GO_KEY:
        print("OPENCODE_GO_API_KEY가 설정되지 않았습니다.")
        return 2
    print("OpenCode Go endpoint:", OPENCODE_GO_BASE)
    print("모델 후보:", _go_candidates("write"))
    ok = []
    for model in _go_candidates("write"):
        try:
            out = _post_opencode_go(
                [{"role": "user", "content": "Reply exactly with OK"}],
                max_tokens=32,
                temperature=0.2,
                timeout=45,
                model=model,
            )
            print(f"  PASS {model}: {out[:80]!r}")
            ok.append(model)
        except Exception as e:
            print(f"  FAIL {model}: {str(e)[:600]}")
    if ok:
        print("사용 가능 모델:", ", ".join(ok))
        return 0
    print("사용 가능한 OpenCode Go 모델을 찾지 못했습니다.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "probe":
        raise SystemExit(probe_go())
    print("writer engines:", [n for n, _ in engines("write")])
    print("review engines:", [n for n, _ in engines("review")])
