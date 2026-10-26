# Release Infrastructure

Date: 2026-10-26
Reviewer: Fable (plan review 2026-10-26, BLOCKING → revised)

## Goal

Prepare the repository for public release and ongoing maintenance: add Python
linting, set up GitHub Actions CI/CD, configure branch rulesets, wire up
Dependabot with auto-merge, and publish both packages.

## Context

Both packages are at v1.0.0, feature-complete, preparing for public release on
PyPI and npm. TypeScript already has ESLint + Prettier + typecheck scripts (101
ESLint errors to fix). Python has no linter. CI/CD, rulesets, and Dependabot
don't exist yet. The remote needs a force-push after a prior history rewrite
(captures/ stripped) — that must happen before rulesets are created.

## Scope

### Step 1 — License

Add a `LICENSE` file (MIT) and declare it in both manifests before any publish.
Without a license, neither registry shows one and consumers legally can't use
the package.

- Root `LICENSE` (MIT, copyright Rose)
- `pyproject.toml`: add `license = {text = "MIT"}` and `license-files = ["LICENSE"]`
- `ts/package.json`: add `"license": "MIT"`

Also add minimal PyPI metadata while here:
- `pyproject.toml`: `description`, `readme = "README.md"`, `[project.urls]`
  (Repository, Documentation). Keep classifiers minimal for now.

Note on import name: `protocol/` installs a top-level module named `protocol`;
a package of that name already exists on PyPI. This is a known naming
decision — accepted for 1.0.0 (the package name `open-legacy-rpc` is fine;
only the import path shadows if someone has both installed). Record as KI,
do not rename in this plan.

### Step 2 — Python linting

Add `ruff` as the Python linter. Configure in `pyproject.toml`.

```toml
[project.optional-dependencies]
dev = ["pytest", "ruff~=0.14"]

[tool.ruff]
line-length = 100
target-version = "py38"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP"]
ignore = ["E501"]   # line-length enforced by formatter separately; code-only

[tool.ruff.lint.isort]
known-first-party = ["protocol", "tools"]

[tool.ruff.extend-exclude]
# generated / Unity project files
extend-exclude = ["experiments/", "UnityProject/", "scripts/"]
```

Lint paths: `protocol/`, `tests/`, `tools/` (all documented, tested entry
points). Do NOT include `experiments/`, `UnityProject/`, `scripts/`.

Only `ruff check` is gating in CI. `ruff format --check` is not gating yet
(separate decision).

Fix strategy: `ruff check --fix` for auto-fixable, then by hand. One commit
for all lint fixes.

Pin ruff to minor version (`ruff~=0.14`) so Dependabot bumps don't introduce
new rules and break CI silently.

### Step 3 — Fix TS lint

101 ESLint errors. Run `pnpm lint:fix` for the 2 auto-fixable, then fix the
rest. Common patterns:
- Unused vars: prefix with `_` or remove
- Missing return types: add them
- `.substr` → `.slice`
- Unnecessary type assertions: remove cast

Run `pnpm test` after to confirm no behaviour change (270-test baseline).
One commit, lint-only.

Note: `no-unnecessary-type-assertion` and `no-floating-promises` fixes can
change runtime behaviour in edge cases — prefer `void` for intentional
fire-and-forget, add `await` elsewhere. Verify full test suite passes after.

Also fix in this step:
- `ts/package.json` `engines.node`: `"^22.0.0"` → `">=22"` (excludes Node 24/26 otherwise)
- Remove `"private": true` from `ts/package.json`

### Step 4 — GitHub Actions workflows

Create `.github/workflows/`.

#### `_checks.yml` (reusable, `workflow_call` only)

```yaml
on:
  workflow_call:

jobs:
  test-python:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - run: pip install -e ".[dev]"
      - run: pytest
      - run: ruff check protocol/ tests/ tools/

  test-typescript:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: ts
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4         # must come BEFORE setup-node
        with:
          package_json_file: ts/package.json
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: pnpm
          cache-dependency-path: ts/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm typecheck
      - run: pnpm lint
      - run: pnpm test
      - run: pnpm build
```

Status check names for branch rulesets: `checks / test-python`,
`checks / test-typescript`. If job names or matrix entries change, the ruleset
required-check names must be updated to match.

#### `ci.yml`

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  checks:
    uses: ./.github/workflows/_checks.yml
```

#### `publish.yml`

Triggered by `push: tags: ['v*.*.*']`.
Also supports `workflow_dispatch` with a `dry_run` boolean input (default
`true`) so publish can be rehearsed without consuming a real version.

Jobs:

**`checks`:** `uses: ./.github/workflows/_checks.yml`

**`verify-version`:** `needs: checks`
Single gate job that checks both manifests *and* confirms they agree with each
other before either publish runs.
```bash
TAG_VERSION="${GITHUB_REF_NAME#v}"
PY_VERSION=$(python3 -c "import tomllib; ...")
TS_VERSION=$(node -p "require('./ts/package.json').version")
assert PY_VERSION == TAG_VERSION
assert TS_VERSION == TAG_VERSION
assert PY_VERSION == TS_VERSION   # manifests agree
```
If any assertion fails, the workflow fails here — both publish jobs are gated.

**`publish-npm`:** `needs: verify-version`
```yaml
permissions:
  contents: read
  id-token: write   # for OIDC trusted publishing
steps:
  - uses: actions/checkout@v4
  - uses: pnpm/action-setup@v4
    with:
      package_json_file: ts/package.json
  - uses: actions/setup-node@v4
    with:
      node-version: '22'
      registry-url: https://registry.npmjs.org  # required for NODE_AUTH_TOKEN
  - run: pnpm install --frozen-lockfile
    working-directory: ts
  - run: pnpm build
    working-directory: ts
  - run: pnpm dlx publint   # pre-flight: checks exports, types, etc.
    working-directory: ts
  - name: Publish (real)
    if: ${{ !inputs.dry_run }}
    run: pnpm publish --no-git-checks
    working-directory: ts
    env:
      NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
  - name: Publish (dry run)
    if: ${{ inputs.dry_run }}
    run: pnpm publish --dry-run --no-git-checks
    working-directory: ts
```

Note on auth: classic npm tokens have a default 90-day expiry; granular access
tokens are preferred. Migrate to npm OIDC trusted publishing (same as PyPI)
once npm's OIDC support is stable in pnpm 10.x. Record `NPM_TOKEN` rotation
in a calendar reminder until then.

**`publish-pypi`:** `needs: verify-version`
```yaml
permissions:
  contents: read
  id-token: write   # OIDC trusted publishing — no PYPI_TOKEN secret needed
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: '3.12'
  - run: pip install build twine
  - run: python -m build
  - run: twine check dist/*
  - uses: pypa/gh-action-pypi-publish@release/v1
    if: ${{ !inputs.dry_run }}
    # OIDC: no password needed; configure trusted publisher on PyPI first
  - name: Dry run (skip actual upload)
    if: ${{ inputs.dry_run }}
    run: echo "Dry run — skipping PyPI upload. twine check passed above."
```

PyPI OIDC trusted publishing setup (one-time, before first publish):
go to pypi.org → Your projects → Publishing → Add a publisher:
  owner: Rose-Vibe, repo: open-legacy-rpc, workflow: publish.yml, env: (none)

**`update-release-latest`:** `needs: [publish-npm, publish-pypi]`
```yaml
permissions:
  contents: write
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
  - run: git push origin HEAD:refs/heads/release-latest
    # Fast-forward only (no --force); tags are always on main so this is safe.
    # No bypass actor needed; the release-latest ruleset only blocks deletions
    # and force-pushes, which this does not do.
```

### Step 5 — Fix pre-existing test failure

`tests/test_network_groups.py::test_recv_rpc_filtered_by_group` fails
deterministically. CI will be red from the first run. Must be resolved in this
plan before Step 4 exit criteria can be met. Options:
- Fix the underlying bug (preferred if straightforward)
- Mark `@pytest.mark.xfail(reason="group filtering not yet implemented", strict=False)`

Investigate and fix or xfail before writing the workflow files, so the first
CI run is green.

### Step 6 — Branch rulesets

Order matters: force-push the history-rewritten `main` to the remote *first*,
then create rulesets.

Configure via `gh api` with JSON bodies committed under `.github/rulesets/`
so they're code-reviewable and re-applicable.

**`main` ruleset:**
- Require PR before merging
- Required status checks: `checks / test-python`, `checks / test-typescript`
  (exact strings — update if job names change)
- Require branches to be up to date before merging
- No force-push
- Bypass: repository admins (for emergencies)
- "Allow auto-merge" must be enabled in repo settings (separate setting)

**`release-latest` ruleset:**
- Block deletions
- Block force-pushes
- No push restriction (GitHub Actions `GITHUB_TOKEN` cannot be added as a
  bypass actor, so restricting to "GitHub Actions only" is not possible;
  linear-history + no-force is sufficient protection since tags are immutable)

**Tag ruleset (`v*.*.*`):**
- Restrict tag creation to repository admins

### Step 7 — Dependabot

**`.github/dependabot.yml`:**
```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    labels: [dependencies]

  - package-ecosystem: npm
    directory: /ts
    schedule:
      interval: weekly
    labels: [dependencies]
    groups:
      dev-dependencies:
        dependency-type: development
      production-dependencies:
        dependency-type: production
    # Cooldown: don't auto-merge packages published < 7 days ago
    # (mitigates supply-chain attacks via typosquatting / package hijack)
    # Set via auto-merge workflow gating on dependabot/fetch-metadata's
    # published-at output.

  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    labels: [dependencies]
```

Also remove the stale `pnpm-lock.yaml` line from `.gitignore` — `ts/pnpm-lock.yaml`
is tracked, and that line is a trap for contributors.

### Step 8 — Dependabot auto-merge

**`.github/workflows/auto-merge.yml`:**

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - uses: dependabot/fetch-metadata@v2
        id: meta
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
      - name: Auto-merge patch and minor updates
        if: steps.meta.outputs.update-type != 'version-update:semver-major'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Notes:
- `GITHUB_TOKEN` works here; no PAT needed. Dependabot-triggered `pull_request`
  events get a read-only token by default — the explicit `permissions:` block
  elevates it to write.
- `--auto` defers the actual merge to GitHub's branch protection; the workflow
  just sets the intent. Do NOT use `--watch`.
- Merges via `GITHUB_TOKEN` do not re-trigger `ci.yml`'s `push: main` run —
  this is fine; the PR run is the gate.
- Major version bumps skip auto-merge and wait for manual review.
- "Allow auto-merge" must be enabled in repo settings (Step 6).
- With "require up to date" and grouped PRs, Dependabot auto-rebases; slower
  but not broken.

## Exit Criteria

- [ ] `LICENSE` exists; both manifests declare `license = "MIT"`
- [ ] `ruff check protocol/ tests/ tools/` exits 0
- [ ] `pnpm lint` in `ts/` exits 0
- [ ] All tests pass: `pytest` 0 failures (excluding any xfail), `pnpm test` 270/270
- [ ] `ts/package.json` does not have `"private": true`; has `"license": "MIT"`
- [ ] `engines.node` is `">=22"` (not `"^22.0.0"`)
- [ ] `_checks.yml`, `ci.yml`, `publish.yml`, `auto-merge.yml` exist and pass
      `actionlint` (or equivalent syntax check)
- [ ] CI (`ci.yml`) passes on a test PR: both `checks / test-python` and
      `checks / test-typescript` green
- [ ] `publish.yml` dry-run (`workflow_dispatch` with `dry_run: true`) passes
      checks, verify-version, and dry-run publish steps — confirms artefacts
      are well-formed without consuming a version
- [ ] `pnpm publish --dry-run` and `twine check dist/*` both pass locally
- [ ] A deliberate version-mismatch tag (e.g., tag says v1.0.1 but manifests
      say 1.0.0) fails `verify-version` before either publish job runs
- [ ] Branch rulesets active: direct push to `main` blocked (as non-admin)
- [ ] Dependabot has opened at least its `github-actions` PRs (first batch)
- [ ] A Dependabot patch/minor PR auto-merges after CI passes
- [ ] A Dependabot major PR does NOT auto-merge
- [ ] PyPI trusted publishing configured (publisher record exists on pypi.org)
