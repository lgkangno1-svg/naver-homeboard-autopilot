# Repository agent policy

## OpenCode Go cost-aware routing

Use only the checked-in OpenCode Go economy pool:

- `opencode-go/mimo-v2.5` for exploration, investigation, scouting, repetitive checks, summaries, and other low-risk sub-agent work;
- `opencode-go/longcat-2.0` as the default/build model for coding, planning, general engineering, auto-build, and deeper implementation work;
- `opencode-go/deepseek-v4-flash` for reviewer/code-reviewer roles, high-risk decisions, or escalation when lower-cost work fails tests or quality gates.

Do not use Flash by default when MiMo or LongCat is adequate. `Kimi K3`, DeepSeek Pro-tier models, MiMo Pro-tier models, and all OpenCode Go models outside the allowlist are forbidden for unattended loops unless the repository owner explicitly changes the policy after a cost/quality review.

Escalate only within the allowlist. Immediately before a paid OpenCode Go request, validate that the final model is allowed; otherwise fail closed without sending the request. Keep `.opencode/opencode.json` aligned with this routing.
