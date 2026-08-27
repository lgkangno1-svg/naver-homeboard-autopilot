from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".opencode" / "opencode.json"
FORBIDDEN = re.compile(r"(?:kimi-k3|deepseek-v4-pro|mimo-v2\.5-pro)", re.IGNORECASE)
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "coverage"}
MARKERS = ("OPENCODE_GO", "opencode_go", "OpenCode Go", "opencode-go", "opencode.ai/zen/go")


def _is_go_model(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("opencode-go/")


def normalize_config() -> bool:
    data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"$schema": "https://opencode.ai/config.json"}
    before = json.dumps(data, sort_keys=True, ensure_ascii=False)
    for key in ("model", "small_model"):
        if _is_go_model(data.get(key)):
            data.pop(key, None)
    provider = data.get("provider")
    if isinstance(provider, dict):
        provider.pop("opencode-go", None)
        if not provider:
            data.pop("provider", None)
    agents = data.get("agent")
    if isinstance(agents, dict):
        for agent_id in list(agents):
            current = agents.get(agent_id)
            if isinstance(current, dict) and _is_go_model(current.get("model")):
                current.pop("model", None)
            if isinstance(current, dict) and not current:
                agents.pop(agent_id, None)
        if not agents:
            data.pop("agent", None)
    after = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if before == after and CONFIG.exists():
        return False
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def verify_no_go_development_routing() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    violations: list[str] = []
    for key in ("model", "small_model"):
        if _is_go_model(data.get(key)):
            violations.append(key)
    provider = data.get("provider")
    if isinstance(provider, dict) and "opencode-go" in provider:
        violations.append("provider.opencode-go")
    agents = data.get("agent")
    if isinstance(agents, dict):
        for agent_id, current in agents.items():
            if isinstance(current, dict) and _is_go_model(current.get("model")):
                violations.append(f"agent.{agent_id}.model")
    if violations:
        raise RuntimeError("OpenCode Go development routing remains: " + ", ".join(violations))


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
    verify_no_go_development_routing()
    hits = scan_forbidden_runtime_models()
    if hits:
        print("Forbidden high-cost OpenCode Go model IDs remain in runtime/config files:")
        for item in hits:
            print(f" - {item}")
        return 2
    print("OpenCode Go development routing disabled; runtime economy-pool checks remain active.")
    if changed:
        print("Normalized .opencode/opencode.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
