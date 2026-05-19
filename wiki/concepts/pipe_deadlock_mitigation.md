---
type: concept
name: Pipe deadlock mitigation
created: 2026-05-17T06:25:11Z
updated: 2026-05-17T06:25:11Z
confidence: 0.70
sources: [snapshot-20260517-061744]
related: []
tier: working
---
# Pipe deadlock mitigation

The architectural decision to use `proc.communicate()` instead of `proc.wait()` to prevent subprocess pipe deadlocks.

## References

- [snapshot: snapshot-20260517-061744]
