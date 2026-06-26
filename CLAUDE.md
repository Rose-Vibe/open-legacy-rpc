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

## Current Objective

Work through the entire experiment matrix, decode all Unity legacy networking
framing, produce a full reference spec (`docs/research/`), and build a
complete Python reference implementation (`protocol/`) of both client and
server. The end state is a Python client that can connect to a Unity server
and a Python server that a Unity client can connect to. Only stop for issues
requiring the user's discretion.

## Architecture

See `docs/architecture/` for design docs.
See `docs/roadmap/` for the broad roadmap.
See `docs/plans/` for active sprint plans.

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

Spawn an Opus-model agent to review the plan. The reviewer should:

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

### When to Use Workflows

For steps that involve fan-out (reviewing multiple files/dimensions in parallel,
running multiple independent checks), use the Workflow tool. For example:

- Reviewing an implementation across correctness, architecture, and test coverage simultaneously
- Running multiple independent checks in parallel

Workflows require explicit opt-in — say "use a workflow" or "ultracode" when requesting.

## Conventions

- Research findings go in `docs/research/` with date-prefixed filenames
- Plans in `docs/plans/`; completed plans move to `docs/plans/archive/`
- ADRs in `docs/adr/`, numbered sequentially
- Notes and informal findings in `docs/notes/`
