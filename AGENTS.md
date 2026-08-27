# Repository agent policy

## OpenCode Go hard cost ceiling

Whenever OpenCode Go is used in this repository, the only permitted model is exactly `opencode-go/deepseek-v4-flash` (`deepseek-v4-flash` at the HTTP API).

This applies to every primary agent, subagent, reviewer, investigator, planner, scout, repair/retry worker, fallback, background task, and unattended/automatic loop. Kimi models, `deepseek-v4-pro`, `mimo-v2.5-pro`, GPT Luna, and every other OpenCode Go model are forbidden for these loops.

Validate the final Go model immediately before network dispatch. If it is not the permitted Flash model, fail closed without making the request; never silently route to a different OpenCode Go model. Keep `.opencode/opencode.json` Flash-only and do not weaken its provider whitelist or per-agent overrides.
