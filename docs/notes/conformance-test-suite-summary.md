# Conformance Test Suite — Summary

> Summarized 2026-06-26

## Goal

A language-agnostic conformance test suite so any implementation of Unity's
legacy networking protocol can verify correctness without using Python as a
runtime dependency. Implementers only need to read/write JSON via stdin/stdout.

## Three Tiers

### Tier 1 — Serde Unit Tests

Pure encode/decode, no networking. A CLI generates test cases as JSON (either
preset edge cases or randomized), the implementer encodes/decodes them and
writes results back as JSON, then the CLI validates. The JSON object
accumulates fields at each stage: generate adds input, the implementer adds
output, validate adds pass/fail + reasons. Everything is stateless — each
stage has all the context it needs in the object itself. Covers individual
encodings (Huffman strings, WriteCompressed, cell serialization, full message
types like UpdateRow/QueryReply, RPC hashes, etc.).

### Tier 2 — Python Peer Tests

Launches a real Python server or client as the "known-good" side. The test
generator produces a sequence of steps (a scripted conversation), where some
steps are for the Python side and some are instructions for the tested
implementation. The tested impl follows its steps, the Python peer validates
behavior after each exchange, and the whole thing fails fast on the first
mismatch. This tests actual wire interop — handshake, message framing,
reliability, ordering — not just serialization.

### Tier 3 — Real Unity Tests

Pre-built scenarios against actual Unity 2018.1.6f1 server/client binaries.
Hardcoded step sequences that mirror a subset of the Tier 2 Python peer
tests. The idea is: if your impl passes Tier 2 but fails Tier 3, you know
the discrepancy is between Python's understanding and Unity's actual
behavior. And since Tier 3 mirrors Tier 2, you can use the Python peer to
debug without needing Unity in the loop every time.

## Cross-Cutting Design

- Standardized JSON schema (with a formal JSON Schema definition) using
  discriminated unions for test-type-specific payloads
- Pipeline model: generate → implement → validate, where each stage appends
  to the same object
- Language-agnostic — an implementer in Rust/C#/Go just needs to read JSON
  from stdin, do the work, write JSON to stdout
- `legacy-net-serde-test` CLI for Tier 1, `legacy-net-peer-test` CLI for
  Tier 2
