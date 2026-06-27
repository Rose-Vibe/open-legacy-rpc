# M13 Section 0: Project Setup

## Goal

Set up a TypeScript project under `ts/` with strict tooling matching the
home-finder project's configuration. Establish the package structure,
test infrastructure, and conformance test bridge.

## Package Structure

```
ts/
├── package.json
├── tsconfig.json
├── tsconfig.base.json
├── eslint.config.mjs
├── .prettierrc.json
├── vitest.config.ts
├── src/
│   ├── index.ts              # Public API barrel export
│   ├── bitstream.ts          # (Section 1)
│   ├── huffman.ts            # (Section 1)
│   ├── raknet/               # (Sections 2–3)
│   ├── unity/                # (Sections 4–5)
│   └── services/             # (Section 6)
├── test/
│   ├── conformance-bridge.ts # Reads JSON test cases, runs TS impl
│   └── ...
└── scripts/
    └── conformance-runner.ts # CLI for piping conformance tests
```

Single package (not a monorepo) — the protocol library is one cohesive unit.
If it later needs to be published as an npm package, the structure supports it.

## TypeScript Configuration

Copy from home-finder's `tsconfig.base.json` with all strict flags:

- `strict: true`
- `noUncheckedIndexedAccess: true`
- `exactOptionalPropertyTypes: true`
- `noPropertyAccessFromIndexSignature: true`
- `noImplicitReturns: true`
- `noFallthroughCasesInSwitch: true`
- `forceConsistentCasingInFileNames: true`
- `verbatimModuleSyntax: true`
- `noImplicitOverride: true`

Target: `ESNext` / `NodeNext` module resolution.
Output: `dist/` with declarations + source maps.

## ESLint Configuration

Flat config (v9+) using `typescript-eslint` strict type-checked preset.
Strip the React/web-specific rules from home-finder — keep only:

- `@typescript-eslint/no-explicit-any: error`
- `@typescript-eslint/no-unsafe-*: error` (all variants)
- `@typescript-eslint/no-floating-promises: error`
- `@typescript-eslint/consistent-type-imports: error`
- `@typescript-eslint/explicit-function-return-type: error`
- `@typescript-eslint/no-unused-vars: error` (with `_` prefix ignore)
- `@typescript-eslint/switch-exhaustiveness-check: error`
- `no-console: error` (use a logger or test-only escape)

## Prettier Configuration

```json
{
  "singleQuote": true,
  "trailingComma": "all",
  "semi": true,
  "printWidth": 100,
  "tabWidth": 2
}
```

No Tailwind plugin needed.

## Test Infrastructure

- **vitest** for unit tests
- **Conformance bridge:** A TypeScript script that reads M12 test JSON from
  stdin, executes the TS implementation for each test case, and writes
  completed JSON to stdout. This plugs into the existing
  `legacy-net-serde-test validate` pipeline.
- The bridge is the primary validation mechanism for sections 1 and 4.

## Node.js Version

Target Node.js 22+ (matching home-finder's `engines` constraint).
Use `node:dgram` for UDP sockets.

## Exit Criteria

- [ ] `ts/` directory exists with all config files
- [ ] `pnpm install` succeeds
- [ ] `pnpm typecheck` passes (empty project)
- [ ] `pnpm lint` passes
- [ ] `pnpm test` runs vitest (with a trivial placeholder test)
- [ ] `pnpm build` produces `dist/` with declarations
- [ ] Conformance bridge script exists (skeleton — actual impl handlers
      are added in subsequent sections)
- [ ] `prettier --check .` passes on all files
