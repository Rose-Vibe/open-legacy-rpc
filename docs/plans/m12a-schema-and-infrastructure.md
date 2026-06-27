# M12a: Schema, CLI Structure, and Pipeline Infrastructure

## Goal

Define the JSON Schema, build the CLI tools, and prove the generate →
implement → validate pipeline works end-to-end with a trivial test case.

## Work

### 1. JSON Schema Definition

Write `conformance/schema/` with formal JSON Schema files:

#### Envelope Schema (`test-envelope.schema.json`)

```jsonc
{
  // Present at all stages
  "testInfo": {
    "testId": "uuid",
    "testName": "human-readable name",
    "testDescription": "what this tests",
    "category": "huffman | writeCompressed | cell | updateRow | ...",
    "mode": "basic | random"
  },

  // Present after generate
  "input": {
    "type": "discriminated by category",
    // ... category-specific fields
  },

  // Present after implementer processes
  "output": {
    "type": "discriminated by category",
    // ... category-specific fields, binary as dataHex
  },

  // Present after validate
  "validation": {
    "pass": true/false,
    "failures": ["reason 1", "reason 2"]
  }
}
```

#### Serde Test Schemas (one per category)

Each category defines its `input` and `output` shapes. Categories are
listed in the M12b sub-plan. The discriminant field is `testInfo.category`.

#### Peer Test Schemas

Each peer test defines a `steps` array with a discriminated union of step
types. Categories are listed in the M12c sub-plan.

### 2. CLI Tools

#### `legacy-net-serde-test`

```
Usage:
  legacy-net-serde-test generate <category> <basic|random> [--count N] [--seed S]
  legacy-net-serde-test validate < responses.json

generate: outputs JSON array of test cases to stdout
validate: reads JSON array of {testInfo, input, output} from stdin,
          outputs JSON array of {testInfo, input, output, validation} to stdout
```

Implementation: `conformance/serde_test_cli.py`

- `generate` dispatches to per-category generator functions
- `validate` dispatches to per-category validator functions
- `--seed` makes random tests reproducible
- `--count` controls how many random tests (default: 10)

#### `legacy-net-peer-test`

```
Usage:
  legacy-net-peer-test generate <category> <basic|random>
  legacy-net-peer-test run [--role server|client] < test.json

generate: outputs JSON array of test scenarios to stdout
run: starts the Python peer process, reads test scenario from stdin,
     executes steps, outputs validation JSON to stdout, exits on first failure
```

Implementation: `conformance/peer_test_cli.py`

### 3. Project Structure

```
conformance/
├── schema/
│   ├── test-envelope.schema.json       # top-level envelope
│   ├── serde/
│   │   ├── huffman.schema.json
│   │   ├── writeCompressed.schema.json
│   │   ├── ... (one per category)
│   └── peer/
│       ├── handshake.schema.json
│       ├── rpc.schema.json
│       ├── ... (one per category)
├── serde_test_cli.py                   # Tier 1 CLI entry point
├── peer_test_cli.py                    # Tier 2/3 CLI entry point
├── generators/
│   ├── __init__.py
│   ├── serde/                          # per-category generate functions
│   │   ├── __init__.py
│   │   ├── huffman.py
│   │   ├── ...
│   └── peer/                           # per-category step generators
│       ├── __init__.py
│       ├── handshake.py
│       ├── ...
├── validators/
│   ├── __init__.py
│   ├── serde/                          # per-category validate functions
│   │   ├── __init__.py
│   │   ├── huffman.py
│   │   ├── ...
│   └── peer/                           # peer test step execution
│       ├── __init__.py
│       ├── handshake.py
│       ├── ...
└── tests/
    ├── test_schema_validation.py       # schema self-tests
    ├── test_serde_pipeline.py          # end-to-end pipeline test
    └── test_peer_pipeline.py           # end-to-end peer test
```

### 4. Pipeline Proof-of-Concept

Implement one trivial serde category (`writeCompressed`) end-to-end:
- Generator produces basic + random test cases
- A "reference implementer" script uses the Python impl to fill `output`
- Validator checks correctness
- Automated test runs the full pipeline

This proves the schema, CLI, and pipeline work before building out all categories.

### 5. Schema Validation

Use `jsonschema` (Python) to validate test objects at each stage. The CLI
validates its own output and the implementer's input. Validation errors
produce clear messages pointing at the failing field.

### 6. Design Conventions (from review)

- **Float specials:** NaN and Infinity use the strings `"NaN"`, `"Infinity"`,
  `"-Infinity"` in JSON. This is documented in the envelope schema, not
  per-category.
- **NDJSON support:** `validate` accepts both a JSON array and newline-
  delimited JSON (one object per line) for shell pipeline friendliness.
- **Seed default:** `--seed` omitted = non-reproducible (random seed).
  When present, output is deterministic.
- **Exit codes:** 0 = all pass, 1 = validation failures, 2 = schema/usage
  error. Both CLIs use the same convention.
- **Multi-client roles:** The `role` field in peer test steps uses string
  prefixes (`"impl"`, `"impl:client1"`, `"impl:client2"`) not a strict
  enum, to support multi-client scenarios in M12c.
- **Numeric types:** Both `float` (32-bit) and `double` (64-bit) are
  valid field types — the schema accommodates both from the start.

## Exit Criteria

- [ ] JSON Schema files cover the envelope and at least one serde category
- [ ] `legacy-net-serde-test generate writeCompressed basic` produces valid JSON
- [ ] `legacy-net-serde-test validate` correctly validates/rejects responses
- [ ] Pipeline test runs end-to-end with the reference implementer
- [ ] `legacy-net-peer-test` CLI skeleton exists (can parse args, read stdin)
- [ ] Schema validation catches malformed test objects
- [ ] `--seed` produces deterministic random output
