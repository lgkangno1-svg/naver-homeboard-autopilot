# Repository agent policy

## Development execution policy

Repository development is performed directly by the active chat/Codex development session. Do not use OpenCode Go for coding, implementation, planning, debugging, refactoring, code review, test repair, repository exploration for development, architecture work, or unattended development loops.

The checked-in `.opencode/opencode.json` intentionally contains no `opencode-go/*` development model routing. Do not reintroduce Go models into build/general/plan/reviewer/code-reviewer/investigator/auto-build/deep agents or equivalent sub-agents.

OpenCode Go may still be used by application/runtime automation when the product itself intentionally calls the Go API for non-development work such as content generation, classification, extraction, research assistance, or other business automation. Runtime use must remain cost-aware and bounded; it does not authorize delegating repository development to OpenCode Go.

When development is requested, perform the work directly in the chat/Codex environment and validate it with the repository's normal tests and checks.
