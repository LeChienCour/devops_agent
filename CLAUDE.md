# CLAUDE.md — Instructions for Claude Code

This file contains the authoritative conventions for Claude Code working inside this repository.
Read it fully before starting any task.

---

## Project Overview

**FinOps Agent** — Autonomous AWS cost waste detection agent built for AWS Community Day 2026.

| Item           | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Goal           | Detect AWS cost leaks and propose remediations via LLM  |
| Languages      | Python 3.12, Terraform >= 1.6                           |
| Orchestration  | LangGraph StateGraph                                     |
| LLM backend    | Amazon Bedrock (Claude Sonnet)                          |
| Tool protocol  | In-process Python tools (`src/agent/tools/`) + MCP wrappers for demo (`src/mcp_servers/`) |
| Source of truth | `PLAN.md`                                              |

---

## Language & Naming Conventions

- **Code and identifiers:** English (variables, functions, classes, modules, comments in code)
- **Comments:** may be written in Spanish when they explain business logic or complex decisions
- **Commit messages:** English only
- **PR descriptions:** English only
- **Documentation files (docs/):** Spanish or English — follow existing file language

---

## Python Conventions

### Formatting and Linting

- Formatter: `ruff format` — **not** black
- Linter: `ruff check` with rules `E, W, F, I, N, UP, B, A, C4, SIM`
- Line length: 100 characters
- Always run `make lint` before committing; CI will reject lint failures

### Type Hints

- Type hints are **required** on all public function signatures and class attributes
- Mypy strict mode must pass: `make typecheck`
- Use `from __future__ import annotations` only when needed for forward refs

### Docstrings

- Google-style docstrings on all public modules, classes, and functions
- Private helpers may have shorter docstrings

### Error Handling

- Define custom exceptions in a module-level `exceptions.py` when a package warrants it
- Never swallow exceptions silently; always log with context before re-raising

### Secrets

- **NEVER hardcode secrets, tokens, ARNs, or account IDs in source code**
- In Lambda: read secrets from AWS SSM Parameter Store at cold-start
- Locally: use `.env` file loaded via `python-dotenv`; `.env` is in `.gitignore`

---

## Test Conventions

### Naming

```
test_<function_name>_<scenario>_<expected_result>

Examples:
  test_gather_node_empty_response_returns_empty_findings
  test_cost_explorer_tool_api_error_raises_tool_exception
  test_slack_notifier_finding_above_threshold_sends_message
```

### Structure

- Unit tests in `tests/unit/` — mock **all** external calls (Bedrock, AWS APIs, Slack)
- Integration tests in `tests/integration/` — use `moto` for AWS, real or VCR for Bedrock
- Fixtures as JSON in `tests/fixtures/`
- Coverage target: > 80% overall; > 70% per phase milestone

### Running

```bash
make test              # unit tests only
make test-integration  # integration tests
make test-all          # full suite with coverage
```

---

## Git Workflow

### Branch Naming

```
feat/fase-N-short-description
fix/short-description
chore/short-description
docs/short-description
```

Examples:
- `feat/fase-0-repo-setup`
- `feat/fase-2-langgraph-mvp`
- `fix/cost-explorer-pagination`

### Commit Format

Conventional Commits in English, with phase tag when applicable:

```
feat(scope): description [Phase N]
fix(scope): description
chore(scope): description
docs(scope): description
test(scope): description
refactor(scope): description
```

Examples:
```
feat(agent): implement plan node with structured JSON output [Phase 2]
fix(cost-explorer): handle pagination for >12 months of data
chore(deps): bump langgraph to 0.2.5
```

### Rules

- **No direct commits to `main`** — always open a PR
- Commit frequently (one logical change per commit)
- At end of each phase: open PR with acceptance criteria checklist from `PLAN.md`

---

## Tools Architecture (ADR-001)

- `src/agent/tools/` — Python functions imported **in-process** by LangGraph nodes. Each module exposes a `TOOLS` list (Bedrock tool_use schema) + the actual callable functions.
- `src/mcp_servers/` — Standalone MCP-compliant wrappers for demo/CLI use (`mcp dev`, `mcp-cli`). They import from `src/agent/tools/` — no logic duplication.
- **Never** add business logic to `mcp_servers/`; it belongs in `agent/tools/`.

## IAM & Security

- Lambda IAM role has **READ-ONLY** permissions in Phases 1–6
- No write/mutating permissions until an explicit human-in-the-loop phase is added
- GitHub MCP server token scope: `repo:read` only
- Lambda is **not** placed inside a VPC (keeps NAT costs at zero)
- Do not log full Bedrock response bodies (may contain sensitive account data)

---

## Before Every Commit Checklist

```
[ ] make format      — no ruff format or ruff check --fix issues
[ ] make lint        — ruff check and ruff format --check both pass
[ ] make typecheck   — mypy strict passes with 0 errors
[ ] make test        — all unit tests pass
[ ] No secrets in diff
[ ] Commit message follows Conventional Commits format
```

---

## Anti-Patterns to Avoid

| Anti-pattern                          | Preferred alternative                                  |
| ------------------------------------- | ------------------------------------------------------ |
| Adding dependencies not in `PLAN.md` | Justify in PR description before adding                |
| Large refactors during feature phases | Schedule for Phase 8 (hardening)                       |
| Over-engineering abstractions early   | Start with the simplest implementation that works      |
| Committing directly to `main`         | Always open a PR, even for trivial changes             |
| Catching bare `Exception`             | Catch specific exceptions; log context before raising  |
| Using `print()` for logging           | Use `structlog` logger                                 |
| Hardcoding resource names/ARNs        | Use `pydantic-settings` config loaded from environment |

---

## Project Phase Reference

See `PLAN.md` §5 for the full phase plan. Current phase is tracked on the active PR.

| Phase | Scope                              |
| ----- | ---------------------------------- |
| 0     | Repository foundation (this PR)    |
| 1     | Terraform infrastructure base      |
| 2     | LangGraph minimum viable agent     |
| 3     | MCP servers                        |
| 4     | Real leak detection (8 scenarios)  |
| 5     | Notifications and UX               |
| 6     | Demo seeding infrastructure        |
| 7     | Talk documentation                 |
| 8     | Hardening and polish               |
