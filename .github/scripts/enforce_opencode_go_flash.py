from __future__ import annotations

import re
from pathlib import Path

PINNED = "deepseek-v4-flash"
ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", ".next", "coverage"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".env", ".example", ".toml"}
MARKERS = ("OPENCODE_GO", "opencode_go", "OpenCode Go", "opencode-go", "opencode.ai/zen/go")

ENV_KEYS = (
    "OPENCODE_GO_MODEL",
    "OPENCODE_GO_REVIEW_MODEL",
    "OPENCODE_GO_VISION_MODEL",
    "OPENCODE_GO_FALLBACK_MODELS",
    "OPENCODE_GO_REVIEW_FALLBACK_MODELS",
    "AI_MODEL_PRIMARY",
    "AI_MODEL_FAST",
)
ASSIGNMENT_NAMES = (
    "PINNED_MODEL",
    "PINNED_OPENCODE_GO_MODEL",
    "OPENCODE_GO_PINNED_MODEL",
    "OTTO_DEFAULT_MODEL",
)
FORBIDDEN_TOKEN = re.compile(
    r"(?:deepseek-v4-pro|gpt-5\.6-luna|kimi-[A-Za-z0-9._-]+|mimo-[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
NON_FLASH_GO_MODEL = re.compile(
    r"opencode-go/(?!deepseek-v4-flash(?:[\"'\s,}\]]|$))[A-Za-z0-9._-]+",
    re.IGNORECASE,
)


def eligible(path: Path) -> bool:
    if path.resolve() == SELF:
        return False
    if path.as_posix().endswith(".github/workflows/opencode-go-flash-guard.yml"):
        return False
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return False
    if path.name.startswith(".env"):
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def enforce(text: str) -> str:
    if not any(marker in text for marker in MARKERS):
        return text
    out = FORBIDDEN_TOKEN.sub(PINNED, text)
    out = NON_FLASH_GO_MODEL.sub(f"opencode-go/{PINNED}", out)
    env_names = "|".join(re.escape(name) for name in ENV_KEYS)
    out = re.sub(rf"(?m)^((?:{env_names})=)[^\n#]*(.*)$", rf"\1{PINNED}\2", out)
    assignment_names = "|".join(re.escape(name) for name in ASSIGNMENT_NAMES)
    out = re.sub(
        rf"\b({assignment_names})(\s*(?::[^=\n]+)?=\s*)['\"][^'\"]+['\"]",
        rf'\1\2"{PINNED}"',
        out,
    )
    out = re.sub(
        r"\b(ai_model_primary|ai_model_fast)(\s*:\s*str\s*=\s*)['\"][^'\"]+['\"]",
        rf'\1\2"{PINNED}"',
        out,
    )

    # Naver runtime last-mile hardening: an explicit unsafe caller model must
    # stop before HTTP dispatch rather than being silently ignored.
    out = out.replace(
        "    del model\n    chosen = OPENCODE_GO_PINNED_MODEL\n    payload = {",
        "    requested_model = (model or OPENCODE_GO_PINNED_MODEL).strip()\n"
        "    if requested_model != OPENCODE_GO_PINNED_MODEL:\n"
        "        raise RuntimeError(\n"
        "            f\"OpenCode Go model blocked by cost policy: {requested_model or '<empty>'}; \"\n"
        "            f\"allowed={OPENCODE_GO_PINNED_MODEL}\"\n"
        "        )\n"
        "    chosen = requested_model\n"
        "    payload = {",
    )
    out = out.replace(
        "    r = requests.post(\n        f\"{OPENCODE_GO_BASE}/chat/completions\",",
        "    if payload.get(\"model\") != OPENCODE_GO_PINNED_MODEL:\n"
        "        raise RuntimeError(\"OpenCode Go request blocked immediately before HTTP dispatch\")\n\n"
        "    r = requests.post(\n        f\"{OPENCODE_GO_BASE}/chat/completions\",",
    )
    return out


def main() -> int:
    changed: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not eligible(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        fixed = enforce(original)
        if fixed != original:
            path.write_text(fixed, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)))
    if changed:
        print("OpenCode Go Flash policy auto-fixed:")
        for item in changed:
            print(f" - {item}")
    else:
        print("OpenCode Go Flash policy already satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
