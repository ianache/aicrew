---
type: concept
name: EXEC-01
created: 2026-05-17T06:19:50Z
updated: 2026-05-17T06:19:50Z
confidence: 0.70
sources: [snapshot-20260517-061744]
related: []
tier: working
---
# EXEC-01

Matched skill executes via Deno subprocess with `--allow-net=<validated-domain>` (domain validated against regex before flag construction), no file I/O permissions, hard 5000ms timeout; process group killed on timeout with no zombie processes.

## References

- [snapshot: snapshot-20260517-061744]
