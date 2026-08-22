# -*- coding: utf-8 -*-
"""LLM 엔진 체인: stealth/ox-alpha(OpenRouter, 무료·비전) → Ollama exaone3.5(로컬) → 사용자 지정 엔드포인트"""
import json, os, re, time

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OLLAMA = "http://localhost:11434"
CUSTOM_URL = os.getenv("LLM_BASE_URL", "").strip()
CUSTOM_MODEL = os.getenv("LLM_MODEL", "").strip()
CUSTOM_KEY = os.getenv("LLM_API_KEY", "").strip()

TEXT_MODEL = "stealth/ox-alpha"


def _post_openrouter(messages, max_tokens, temperature, timeout):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={"model": TEXT_MODEL, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens,
              "reasoning": {"effort": "low"}},
        timeout=timeout,
    )
    if r.status_code in (402, 429):
        raise RuntimeError(f"openrouter {r.status_code}")
    r.raise_for_status()
    return r.json()["choices"][0]["message"].get("content") or ""


def _post_ollama(messages, max_tokens, temperature, timeout):
    r = requests.post(
        f"{OLLAMA}/v1/chat/completions",
        json={"model": "exaone3.5", "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _post_custom(messages, max_tokens, temperature, timeout):
    headers = {"Content-Type": "application/json"}
    if CUSTOM_KEY:
        headers["Authorization"] = f"Bearer {CUSTOM_KEY}"
    r = requests.post(f"{CUSTOM_URL.rstrip('/')}/chat/completions", headers=headers,
                      json={"model": CUSTOM_MODEL, "messages": messages,
                            "temperature": temperature, "max_tokens": max_tokens},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def engines():
    chain = []
    if OPENROUTER_KEY:
        chain.append(("ox-alpha", _post_openrouter))
    if CUSTOM_URL and CUSTOM_MODEL:
        chain.append(("custom", _post_custom))
    try:
        if requests.get(f"{OLLAMA}/api/tags", timeout=3).status_code == 200:
            chain.append(("ollama-exaone", _post_ollama))
    except Exception:
        pass
    return chain


def chat(messages, max_tokens=4000, temperature=0.8, timeout=300):
    """엔진 체인을 순서대로 시도, 첫 성공 응답 반환"""
    errs = []
    for name, fn in engines():
        for attempt in range(2):
            try:
                out = fn(messages, max_tokens, temperature, timeout)
                if out and out.strip():
                    return out.strip()
            except Exception as e:
                errs.append(f"{name}:{str(e)[:80]}")
                time.sleep(2)
    raise RuntimeError("모든 LLM 엔진 실패: " + " | ".join(errs))


def chat_json(messages, max_tokens=6000, temperature=0.7, retries=2):
    """JSON 응답 요청 후 파싱. 실패 시 오류 메시지를 피드백해 재요청."""
    last = None
    msgs = list(messages)
    for i in range(retries + 1):
        out = chat(msgs, max_tokens=max_tokens, temperature=min(0.5, temperature))
        m = re.search(r"\{.*\}|\[.*\]", out, re.S)
        if m:
            try:
                return json.loads(m.group())
            except Exception as e:
                last = e
        msgs = msgs + [
            {"role": "assistant", "content": out[:2000]},
            {"role": "user", "content":
                f"위 출력은 JSON 파싱에 실패했다 (오류: {last}). "
                "문자열 안에 이스케이프 안 된 쌍따옴표가 없게 고치고, 설명 없이 유효한 JSON만 다시 출력하세요."},
        ]
    raise RuntimeError(f"JSON 파싱 실패: {last}")


def vision(image_b64_url, prompt, max_tokens=3000, temperature=0.2):
    """이미지 입력 (data:image/jpeg;base64,... 형식). ox-alpha만 비전 지원."""
    if not OPENROUTER_KEY:
        raise RuntimeError("비전은 OpenRouter 키 필요")
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={"model": TEXT_MODEL, "max_tokens": max_tokens, "temperature": temperature,
              "messages": [{"role": "user", "content": [
                  {"type": "image_url", "image_url": {"url": image_b64_url}},
                  {"type": "text", "text": prompt}]}]},
        timeout=240,
    )
    r.raise_for_status()
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("엔진 체인:", [n for n, _ in engines()])
    print(chat([{"role": "user", "content": "'전기차'로 짧은 문장 하나 만들어봐"}], max_tokens=2000))
