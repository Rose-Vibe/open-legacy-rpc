# M12: Language-Agnostic Conformance Test Suite

## Goal

Build a conformance test suite that any implementation of Unity's legacy
networking protocol can run to verify correctness, regardless of language.
Implementers interact via JSON on stdin/stdout — no Python dependency at runtime.

## Motivation

The Python reference implementation exists to prove the protocol is understood.
The conformance suite exists so other implementations (Rust, C#, Go, etc.) can
verify they produce identical wire output and interoperate correctly without
reading the Python code.

## Architecture

Three tiers, each progressively higher-level:

1. **Serde unit tests** — pure encode/decode, no networking
2. **Python peer tests** — interop against a live Python server/client
3. **Unity peer tests** — interop against real Unity 2018.1.6f1 binaries

Two CLI tools:

- `legacy-net-serde-test` — Tier 1 (generate + validate)
- `legacy-net-peer-test` — Tier 2 and 3 (generate + run)

### JSON Pipeline Model

Every test flows through a stateless pipeline where each stage appends to
the same JSON object:

```
generate → { testInfo, input }
                ↓
implementer  → { testInfo, input, output }
                ↓
validate     → { testInfo, input, output, validation }
```

A formal JSON Schema governs the envelope and each test type's discriminated
union payload.

## Sub-Plans

| Sub-plan | Scope | File |
|----------|-------|------|
| M12a | Schema, CLI structure, pipeline infrastructure | `m12a-schema-and-infrastructure.md` |
| M12b | Serde unit tests (all encoding categories) | `m12b-serde-tests.md` |
| M12c | Python peer tests (server/client interop) | `m12c-peer-tests.md` |
| M12d | Unity peer tests (real Unity binaries) | `m12d-unity-tests.md` |

## Implementation Order

```
M12a (schema + infra)  → foundation everything else builds on
M12b (serde tests)     → pure encoding, no networking dependency
M12c (peer tests)      → requires working Python server/client
M12d (unity tests)     → requires Unity builds, mirrors subset of M12c
```

M12a must be complete first. M12b can proceed independently after M12a.
M12c depends on M12a. M12d depends on M12c (mirrors its scenarios).

## Security Constraint

`Network.InitializeSecurity()` must NEVER be called in experiments.

## Exit Criteria

- [ ] JSON Schema published and validated
- [ ] `legacy-net-serde-test generate` and `validate` work end-to-end
- [ ] `legacy-net-peer-test generate` and `run` work end-to-end
- [ ] All serde categories have preset + random tests
- [ ] Python peer tests cover handshake, RPC, state sync, master server
- [ ] Unity peer tests mirror a representative subset of Python peer tests
- [ ] A non-Python "implementer" stub (e.g., a shell script using the Python
  reference impl) can run the full pipeline to prove the interface works
