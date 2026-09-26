# ADR 0004: In-Memory Sessions

## Status
Accepted

## Context
After login, we need to track which user is making API requests. Options include JWT tokens, database-backed sessions, or in-memory dictionaries.

## Decision
Use an in-memory Python dict mapping 64-character hex tokens to user objects. On login, generate a token and store it. On each request, validate the Bearer token against the dict. Sessions are lost on server restart.

## Consequences
**Positive:**
- Zero infrastructure (no Redis, no session table).
- Simple to implement and debug.
- Adequate for single-process MVP deployment.

**Negative:**
- Sessions lost on server restart (acceptable for MVP).
- Not scalable to multiple processes/servers.
- No token expiry in MVP (potential security concern for production).