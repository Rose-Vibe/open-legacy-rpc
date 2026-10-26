# Rename Public Package Identity to `open-legacy-rpc`

## Context

Before releasing this project publicly, the user wants the public-facing
package/repo identity to drop "Unity" from its name, to avoid using the
Unity trademark in a project name — especially for a clean-room reverse
engineering project. After a naming discussion (see chat history, not a
doc), the user chose **`open-legacy-rpc`**: it matches the project's
primary subject (Unity's legacy RPC framing on top of RakNet) most
closely of the candidates considered, and is confirmed available and
uncollided on npm, PyPI, and GitHub (checked 2026-07-13).

This plan covers renaming the **outward package/project identity only**.
It does not cover a full sweep of every internal "Unity" reference in
code or docs — see "Explicitly Out of Scope" below for why, and what to
do instead.

## Principle: brand name vs. descriptive reference

Established in prior discussion with the user and carried into this plan:

- **Change**: anything that is the package/project's own name or brand —
  what shows up on an npm/PyPI listing, a GitHub repo header, or a
  README/CLAUDE.md title.
- **Leave alone**: anything that *describes* Unity's actual protocol as a
  factual matter (e.g., "this decodes Unity's `NetworkView` RPC wire
  format") — this is nominative/descriptive use, not branding, and
  scrubbing it would make the technical docs harder to read for no
  trademark-risk reduction. (Not legal advice — general reasoning per
  the prior discussion, not a legal conclusion.)

## Changes

### 1. Package manifests

- `pyproject.toml`: `name = "unity-legacy-networking"` →
  `name = "open-legacy-rpc"`. The importable module stays `protocol` (the
  `[tool.setuptools.packages.find]` include is already `["protocol*"]`,
  unrelated to the distribution name) — no import-site changes anywhere.
- `ts/package.json`: `"name": "unity-legacy-networking"` →
  `"name": "open-legacy-rpc"`. Confirmed via grep that no source file
  under `ts/src/` or `ts/test/` references the package name string
  (imports are all relative) — this is a single-line change with no
  ripple into source. Note `"private": true` is already set, so this
  rename has no effect on npm-listing visibility until that's flipped at
  actual publish time — expected, not a gap in this plan.

### 2. README.md

- H1 title: `# Unity Legacy Networking Reversed` → `# open-legacy-rpc`.
- Usage example (currently `import { UnityServer, createUdpSocket } from
  'unity-legacy-networking';`) → update the module specifier to
  `'open-legacy-rpc'`. `UnityServer`/`createUdpSocket` are actual exported
  identifier names from the TS source (`ts/src/index.ts`) — those do NOT
  change (see Out of Scope).
- Add a short trademark disclaimer near the top (e.g. under the tagline):
  *"Unity is a trademark of Unity Technologies. This project is
  independent, clean-room reverse-engineered, and not affiliated with or
  endorsed by Unity Technologies."* This was proposed in the earlier
  naming discussion as a cheap, standard addition alongside the rename.
- The rest of the README's prose (which describes Unity's protocol
  factually — "Unity's legacy RPC networking stack", "Unity 2018.1.6f1",
  etc.) is left unchanged — descriptive, not branding.
- The link to `docs/research/unity-legacy-networking-wire-format.md`
  keeps its current filename/path *and* its current link text ("Unity
  Legacy Networking Wire Format" — the spec doc's own title) unchanged
  (see Out of Scope, item 2). Called out explicitly so the executor
  doesn't "helpfully" reword the link text while touching this file for
  the H1/disclaimer/import-example edits.

### 3. CLAUDE.md

- H1 title: `# Unity Legacy Networking Reversed` → `# open-legacy-rpc`,
  for consistency with README.md, since this file is checked into the
  repo and will be publicly visible.
- No other changes — the body already describes Unity's protocol
  descriptively throughout (module names, field names, historical
  narrative), which is out of scope per the principle above.

## Downstream Consumer Impact: distance-server

`ts/package.json`'s `name` field is not just cosmetic — the sibling
project `/home/server-mint/distance-server` depends on this package by
that exact name via a `file:` link:

- `distance-server/brain/package.json` line 26:
  `"unity-legacy-networking": "file:../../unity-legacy-networking-reversed/ts"`
- 10+ files under `distance-server/brain/src/distance/` import
  `from 'unity-legacy-networking'`.

Renaming `ts/package.json`'s `name` to `open-legacy-rpc` means the
dependency key in `distance-server/brain/package.json` no longer matches
the target package's own declared name, which some pnpm versions warn or
error on. **This plan does not edit anything under
`/home/server-mint/distance-server`** — that's a separate repo with its
own actively-worked-on Claude Code session (the `reference-twin-torch`
status-inbox thread), and changing it isn't this plan's call to make
unilaterally. Instead:

- Exit criteria (below) include actually running `pnpm install` in
  `distance-server/brain` after the local rename lands, to find out
  empirically whether it still resolves — not assumed either way.
- If it breaks (or even if it doesn't but the name mismatch is
  confusing), the necessary follow-up — updating the dependency key and
  the ~10 import specifiers in `distance-server/brain` to
  `open-legacy-rpc` — is flagged to the user as a **separate, coordinated
  change in that other repo**, ideally communicated to the
  `reference-twin-torch` session via status-inbox rather than done here.

## Explicitly Out of Scope (and why)

1. **Internal code/module names** (`protocol/unity_protocol.py`,
   `ts/src/unity/*`, `unity_client.py`, `unity_server.py`, etc.) — these
   are internal implementation detail, not public package branding.
   Renaming them is a large, purely-mechanical, high-diff-noise change
   with no trademark-risk reduction, since they're never the name a user
   installs or searches for.
2. **`docs/research/unity-legacy-networking-wire-format.md`'s filename**
   — referenced by ~15+ files including several archived, dated plans.
   Its name factually describes its content (Unity's wire format spec);
   renaming it would require touching every historical cross-reference
   for no branding benefit, and would blur the "append corrections, don't
   rewrite history" convention already established for this repo's
   archived docs (see the `method_tag` saga's erratum pattern).
3. **Dated research/plan docs under `docs/research/` and
   `docs/plans/archive/`** — several contain literal, historical mentions
   of the old package name (e.g. in old import snippets). These are a
   point-in-time record of what was true when written; retroactively
   editing them would misrepresent the historical record. Only the
   currently-live identity surfaces (manifests, README, CLAUDE.md) are in
   scope.
4. **The local working directory name**
   (`/home/server-mint/unity-legacy-networking-reversed`) and **the
   GitHub repo name** — there is currently no git remote configured (this
   is a local-only repo pre-publish), so "repo name" is not yet a file to
   edit; it's a decision for whenever the user actually creates/pushes
   the public repo, at which point they'd name it `open-legacy-rpc`
   directly. Renaming the *local* directory out from under the current
   session would also be disruptive (breaks the active session's cwd and
   any external shortcuts) and isn't requested here — flagged as a
   separate manual step for the user to do on their own schedule, not
   bundled into this plan.
5. `docs/notes/unity-headless-builds.md`'s literal absolute path
   (`/home/server-mint/unity-legacy-networking-reversed/UnityProject`) —
   depends on item 4 (the local directory rename) which is out of scope
   here; revisit only if/when that directory is ever actually renamed.

## Exit Criteria

- [x] `pyproject.toml` `name` field is `open-legacy-rpc`.
- [x] `ts/package.json` `name` field is `open-legacy-rpc`.
- [x] `README.md` H1 is `open-legacy-rpc`; usage example imports from
      `'open-legacy-rpc'`; a trademark disclaimer is present.
- [x] `CLAUDE.md` H1 is `open-legacy-rpc`.
- [x] `grep -rn "unity-legacy-networking" pyproject.toml ts/package.json
      CLAUDE.md` returns zero matches. (README.md is checked separately,
      below, since it legitimately retains one match.) Confirmed: zero
      matches (grep exit code 1).
- [x] `grep -n "unity-legacy-networking" README.md` returns exactly one
      match: the wire-format spec doc link (path + title text
      unchanged). Not zero — a zero-match result here would mean the spec
      link got incorrectly edited. Confirmed: exactly one match, the spec
      link at line 49.
- [x] `git grep -n "unity-legacy-networking" -- ':!captures'` (tracked
      files only, so build artifacts like a stale `*.egg-info/PKG-INFO`
      don't produce false positives; `captures/` excluded because ~180
      tracked capture `.log` files embed the absolute working-directory
      path, e.g. `Found path: /home/server-mint/unity-legacy-networking-
      reversed/UnityProject/...` — same category as the local-directory-
      name item in Out of Scope, not a doc/code reference) over the whole
      repo returns matches in exactly: dated docs under `docs/research/`
      and `docs/plans/archive/`, live docs that cross-reference the
      wire-format spec *filename* (`docs/research/spec-status.md`,
      `docs/plans/method-tag-collision-guard.md`, `docs/plans/method-tag-
      real-derivation-fix.md`, `docs/plans/large-delta-cross-assembly-
      index-test.md`, and any others of the same kind),
      `docs/notes/unity-headless-builds.md`'s absolute path, README.md's
      one spec-link match, and this plan document itself (once it's
      committed — it's currently untracked, so `git grep` won't surface
      it until then) — nothing else. If a plain (non-`git`) `grep -r`
      is used instead, expect it to also surface a stale
      `unity_legacy_networking.egg-info/` directory from a prior local
      `pip install -e .`; delete that stale directory rather than
      treating it as a real finding. Confirmed: matches fall exactly into
      the expected set (also including `docs/plans/archive/m16-api-
      improvements.md`'s two archived import-snippet lines, correctly
      covered by the "dated/archive" category). Deleted the stale
      `unity_legacy_networking.egg-info/` directory (it was gitignored).
- [x] Python test suite and TS vitest/tsc still pass after the manifest
      renames (sanity check that changing the distribution `name` fields
      doesn't break anything — it shouldn't, since neither is imported by
      name anywhere in source, but worth confirming rather than
      assuming). Confirmed: TS `tsc --noEmit` clean, vitest 258/258
      passed. Python: 256/257 passed; the one failure
      (`test_recv_rpc_filtered_by_group`) is the pre-existing, already-
      documented network-groups filtering bug, unrelated to this rename.
- [x] `pip install -e .` succeeds when run from the **repo root** (not
      `protocol/`, despite the README's current Quick Start snippet —
      that's a pre-existing, unrelated inconsistency between the
      snippet and where `pyproject.toml` actually lives; not fixed by
      this plan, just don't let the exit check inherit the bug).
      `pnpm install` in `ts/` still succeeds with the renamed manifest.
      Confirmed both. (The environment is a PEP 668 "externally managed"
      one; reinstalling required `--break-system-packages`, matching how
      the package was evidently installed originally — unrelated to the
      rename itself.) `pip show open-legacy-rpc` now reports the new
      name/editable location correctly.
- [x] Ran `pnpm install` in `distance-server/brain` after the local
      rename and recorded whether it still resolves cleanly (see
      "Downstream Consumer Impact" above) — reported to the user either
      way, not silently assumed. Result: the `unity-legacy-networking`
      dependency key still resolved and linked correctly to
      `unity-legacy-networking-reversed/ts` — pnpm resolves `file:` deps
      by path, not by cross-checking the target's own `package.json`
      `name` field, so this rename did **not** break distance-server's
      install. `pnpm install` did fail overall, but on a separate,
      pre-existing, unrelated error (`ERR_PNPM_WORKSPACE_PKG_NOT_FOUND`
      for `@distance-level-db/primitives`, a missing workspace package in
      that repo's own monorepo setup) — not caused by, or fixed as part
      of, this plan.
