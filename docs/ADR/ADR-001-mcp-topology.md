# ADR-001: MCP Topology — In-Process Tools vs Out-of-Process MCP Servers

**Status:** Accepted  
**Date:** 2026-04-20  
**Deciders:** Diego Sandoval

---

## Context

The FinOps agent needs to call AWS APIs (Cost Explorer, CloudWatch, EC2, etc.) as tools during LangGraph execution. MCP (Model Context Protocol) was designed as an **out-of-process** protocol (stdio or HTTP transport). Running MCP servers as separate processes from inside Lambda adds serialization overhead and complicates the deployment unit.

## Decision

**Two-layer architecture:**

1. **`src/agent/tools/`** — Python functions imported directly (in-process). These are the functions the LangGraph nodes actually call. Tool schemas for Bedrock `tool_use` are defined here as `TOOLS` lists.

2. **`src/mcp_servers/`** — Standalone MCP-compatible server wrappers. Each server in this directory can be run independently via `mcp-cli` for demo/debugging. They import from `src/agent/tools/` and re-expose the same functions with MCP protocol compliance.

## Consequences

- **Positive:** Zero IPC overhead in Lambda; single deployment zip; easier unit testing (just call functions).
- **Positive:** MCP narrative preserved for the talk — each server is runnable standalone, demo-able with `mcp dev`.
- **Negative:** Slight code duplication (schema defined in `tools/` and re-exported in `mcp_servers/`).
- **Accepted:** Duplication is minimal (just `TOOLS` list forwarding); correctness and performance outweigh it.
