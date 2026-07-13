# Unity Legacy Networking Reversed

Reverse-engineering Unity's legacy RPC networking (`NetworkView` / `[RPC]` /
`OnSerializeNetworkView`) — the stack last supported in Unity 2018.1.6f1.
The transport underneath is RakNet 3.731 (open source); the target is
**Unity's framing on top of RakNet**, which is undocumented.

## Key References

- `docs/notes/unity-2018.1.6f1-headless-install.md` — installing the editor
- `docs/notes/unity-headless-builds.md` — headless builds
- `docs/notes/raknet-ip-limit-crash.md` — RakNet IP limit & network namespace fix
- `docs/notes/unity-raknet-capture-decode-playbook.md` — capture & differential analysis method

## PCAP Decoder Tool

`tools/decode_pcap.py` decodes pcap/pcapng files into structured JSON
(RakNet → Unity → game-specific). Accepts an optional JSON config via
`--config` or stdin for server port, method signatures, and view names.
Output uses discriminated unions; game-specific data is marked
`not_deserialized` for downstream post-processing.

```bash
python3 tools/decode_pcap.py capture.pcap [--config config.json] [--compact]
```

## Network Namespace

Unity's RakNet crashes when the host has >10 IPv4 addresses. The repo
includes `netns-setup.sh` / `netns-teardown.sh` to create a clean namespace.
Both the server and client run inside the namespace; traffic is observable
from the host via `tshark -i veth-unet-h`.

```bash
sudo bash netns-setup.sh                          # one-time
sudo ip netns exec unitynet ./Player.x86_64 ...   # run Unity inside
tshark -i veth-unet-h -f 'udp' -w /tmp/unity.pcap   # capture from host
sudo bash netns-teardown.sh                        # clean up
```

## Status

The wire format is fully decoded and documented in `docs/research/`. Both
Python (reference) and TypeScript (production) implementations are complete
with client and server. See `docs/plans/` for active sprint plans.

## Development Workflow

Every significant unit of work follows this pipeline. Do not skip steps.

**This pipeline is autonomous.** When the user says to work through N milestones or
tasks, proceed through all of them without asking for confirmation between steps.
The plan-review and implementation-review loops are the quality gates — trust them.
Only stop and ask the user if:

- A fundamental architectural conflict or ambiguity arises that the reviewer cannot resolve
- A decision has significant irreversible consequences not covered by existing plans
- Tests reveal a systemic issue that suggests the plan itself is wrong
- Something would be unsafe or destructive (e.g., data loss, breaking a working system)

Do not pause to show progress, ask "should I continue?", or request approval between
milestones. The user will interrupt if they want to redirect.

### Step 1: Plan

Write or update a plan document in `docs/plans/` describing what will be built,
why, and what the exit criteria are. Plans reference the relevant section of
the architecture doc and the roadmap.

### Step 2: Plan Review

Spawn a Fable-model agent to review the plan. The reviewer should:

- Check consistency with the architecture doc
- Identify missing edge cases or exit criteria
- Flag over-engineering or scope creep
- Suggest concrete improvements

Iterate on the plan until the reviewer approves with no blocking concerns.

### Step 3: Implement

Implement the plan. Write code, tests, and any needed configuration.

### Step 4: Implementation Review

Spawn an Opus-model agent to review the implementation. The reviewer should:

- Read the plan and the diff
- Check that the implementation matches the plan
- Look for correctness bugs, missing edge cases, and architectural violations
- Verify test coverage of the exit criteria
- Flag anything that should be fixed before committing

Iterate on the implementation until the reviewer approves.

### Step 5: Test and Commit

- Run the relevant test suite
- Ensure all tests pass
- Create a commit with a clear message describing what was built and why

### Subagent Etiquette

Do not send "hurry up" or "wrap up now" messages to subagents. If you want
to check a subagent's progress, read the last 5 lines of its transcript
file silently. Only message a subagent if you have new information to
give it or need to change its task.

If a subagent goes idle without sending results, check the end of its
transcript file manually (in the `subagents/` directory under the session)
rather than waiting or messaging it.

### When to Use Workflows

For steps that involve fan-out (reviewing multiple files/dimensions in parallel,
running multiple independent checks), use the Workflow tool. For example:

- Reviewing an implementation across correctness, architecture, and test coverage simultaneously
- Running multiple independent checks in parallel

Workflows require explicit opt-in — say "use a workflow" or "ultracode" when requesting.

## Conventions

- Research findings go in `docs/research/` with date-prefixed filenames
- Plans in `docs/plans/`; completed plans move to `docs/plans/archive/`
- Notes and informal findings in `docs/notes/`

### Method-Index / Subsequent-Use Testing

For subsequent-use RPC dispatch and method-index calculation work, consistently
consider — and where possible test with — two genuinely different assemblies,
under the explicit model that assembly A has no way of knowing assembly B's
internal method indices, ordering, or count. A single shared build (or two
builds differing by only a small, artificial index shift) can hide bugs that
only appear when the two sides' static index tables have diverged for real
reasons (different RPC method sets, different counts, different ordering).

**Do not re-attempt deriving the static method-index formula from scratch.**
A full day of dedicated investigation (see
`docs/research/2026-06-27-method-index-investigation.md`) could not fully
solve it — the `base_offset` term has a known counterexample and no general
formula was found; only per-build empirical extraction (Cecil-based)
proved reliable. (An earlier version of this note briefly asserted that
"0x07 does not carry a usable dispatch index" — that was itself wrong,
traced to a bit-layout bug in `decode_batch_index` (fixed; see
`docs/research/2026-07-13-batch-index-decoder-was-broken.md`). Correctly
decoded, 0x07 *does* carry the announcer's own real static dispatch
index, and real Unity uses it via an adoption recipe confirmed
direction-resolved against a real Unity↔Unity capture: the sender of a
subsequent-use RPC encodes it using the index the *receiver* previously
announced; the receiver decodes inbound subsequent-use via the index *it*
previously announced. This does not change the guidance below — 0x07
learning is a *runtime dispatch mechanism*, not a way to derive the
static per-build formula itself; the formula remains unsolved and
per-build empirical extraction remains the only reliable way to obtain
a build's own table in the first place.) Treat re-deriving the formula as
an absolute last resort, to be attempted only if it turns out to be
strictly necessary even in the differing-assembly case — prefer
per-build empirical extraction first.
