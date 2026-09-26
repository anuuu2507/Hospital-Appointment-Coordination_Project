# ADR 0001: Use Gemini Function Calling as Agent Backbone

## Status
Accepted

## Context
We need an AI agent that can understand natural language requests and perform hospital appointment operations (search, book, cancel, reschedule). The agent must reliably map user intent to structured actions without hallucinating data.

## Decision
Use Google Gemini 2.0 Flash with function calling. Define 9 Python tool functions that Gemini can invoke. The agentic loop dispatches function calls and feeds results back to Gemini until a plain-text response is produced.

## Consequences
**Positive:**
- LLM handles language understanding; Python handles business logic.
- Function calls are structured and debuggable.
- Business rules cannot be bypassed via prompt injection.

**Negative:**
- Requires Gemini API key and network access.
- Token costs per conversation turn.
- Gemini may occasionally call wrong tools or misparse arguments.