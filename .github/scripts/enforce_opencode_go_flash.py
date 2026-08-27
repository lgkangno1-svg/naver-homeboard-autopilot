from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".opencode" / "opencode.json"
ALLOWED = ("mimo-v2.5", "longcat-2.0", "deepseek-v4-flash")
DEFAULT_MODEL = "longcat-2.0"
SMALL_MODEL = "mimo-v2.5"
AGENT_MODELS = {
    "build": "longcat-2.0",
    "plan": "longcat-2.0",
    "general": "longcat-2.0",
    "explore": "mimo-v2.5",
    "reviewer": "deepseek-v4-flash",
    "investigator": "mimo-v2.5",
    "code-reviewer": "deepseek-v4-flash",
    "auto-build": "longcat-2.0",
    "deep-sol": "longcat-2.0",
    "fast-luna": "mimo-v2.5",
    "go-scout": "mimo-v2.5",
}
FORBIDDEN = re.compile(r"(?:kimi-k3|deepseek-v4-pro|mimo-v2\.5-pro)", re.IGNORECASE)
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "coverage"}
MARKERS = ("OPENCODE_GO", "opencode_go", "OpenCode Go", "opencode-go", "opencode.ai/zen/go")


def normalize_config() -> bool:
    data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"$schema": "https://opencode.ai/config.json"}
    before = json.dumps(data, sort_keys=True, ensure_ascii=False)
    data["model"] = f"opencode-go/{DEFAULT_MODEL}"
    data["small_model"] = f"opencode-go/{SMALL_MODEL}"
    data["subagent_depth"] = 1
    provider = data.setdefault("provider", {})
    go = provider.setdefault("opencode-go", {})
    go["whitelist"] = list(ALLOWED)
    go.pop("blacklist", None)
    agents = data.setdefault("agent", {})
    for agent_id, model in AGENT_MODELS.items():
        current = agents.get(agent_id)
        if not isinstance(current, dict):
            current = {}
            agents[agent_id] = current
        current["model"] = f"opencode-go/{model}"
    after = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if before == after and CONFIG.exists():
        return False
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def scan_forbidden_runtime_models() -> list[str]:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path == CONFIG or path.resolve() == Path(__file__).resolve() or path.suffix.lower() not in CODE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(marker in text for marker in MARKERS) and FORBIDDEN.search(text):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def main() -> int:
    changed = normalize_config()
    hits = scan_forbidden_runtime_models()
    if hits:
        print("Forbidden high-cost OpenCode Go model IDs remain in runtime/config files:")
        for item in hits:
            print(f" - {item}")
        return 2
    print("OpenCode Go economy policy OK: MiMo for cheap workers, LongCat for build, Flash for review.")
    if changed:
        print("Normalized .opencode/opencode.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
