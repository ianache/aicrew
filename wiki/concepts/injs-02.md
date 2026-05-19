---
type: concept
name: INJS-02
created: 2026-05-17T06:19:50Z
updated: 2026-05-17T06:19:50Z
confidence: 0.70
sources: [snapshot-20260517-061744]
related: []
tier: working
---
# INJS-02

LLM payload is validated against `skill.json` `input_schema` (JSON Schema) before Deno fires — missing required fields block the call and return a structured correction request to the agent (no infrastructure call made).

## References

- [snapshot: snapshot-20260517-061744]
