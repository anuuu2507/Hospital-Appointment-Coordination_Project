# ADR 0003: Permissions Enforced in Tool Layer

## Status
Accepted

## Context
The system has two roles (patient, staff) with different capabilities. We need to prevent patients from accessing staff functions and vice versa.

## Decision
Each tool function accepts `caller_id` and `caller_role` parameters injected server-side. The tool checks `caller_role` before executing and returns an error if the role is unauthorized. The LLM never controls role assignment.

## Consequences
**Positive:**
- Role checks are in Python code, not LLM prompts.
- Cannot be bypassed by clever prompt engineering.
- Clear, auditable permission model.

**Negative:**
- Each tool must explicitly check roles (boilerplate).
- No fine-grained permissions beyond role (e.g., per-hospital scoping) in MVP.