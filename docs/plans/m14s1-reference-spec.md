# M14 S1: Reference Spec Update

## Goal

Bring the wire format reference spec (`docs/research/unity-legacy-networking-wire-format.md`)
fully up to date with all findings from M8–M13. The spec is the canonical
document for anyone building a Unity legacy networking implementation. It must
be accurate, self-consistent, and complete.

## Background

The spec was written incrementally across milestones. Some sections have stale
descriptions that were superseded by later findings:

- **§2.3 (0x81 message):** Currently says "field meanings are not fully reversed"
  but spec-status.md records that all fields were decoded in M10a (constant_1=1,
  constant_0=0, player_index, viewid_stride=50, constant_2=2, block_start, block_end).
  §7.1 already has the correct table — §2.3 needs to match it.
- **§15 is duplicated:** "NetworkPlayer as RPC Parameter" and "Disconnect Cleanup"
  both use section number 15. The second should be §16.
- **§2.1 offline phase:** The 0x09 layout lists "server address" but it's
  actually the client's own address echoed. Should clarify.
- **Cross-references:** Some sections (e.g., §10, §14) reference other sections
  but the references may be inconsistent after renumbering.

## Scope

### In Scope

- Fix §2.3 to use the decoded 0x81 field names and match §7.1
- Fix §15/§16 numbering collision
- Verify all cross-references are consistent
- Verify all section content matches spec-status.md's "resolved" items
- Add any missing details from M10–M13 experiments
- Ensure the "worked example" in §4.3 is still correct
- Update appendix references if needed

### Out of Scope

- Adding new sections for undiscovered protocol features
- Changing the structure or organization of the spec (just content accuracy)
- Code changes

### Also Fix

- `docs/research/spec-status.md` §2.3 status: change "Mostly complete"
  to "Complete" — the note below it already says "All 0x81 fields decoded
  (M10a)" but the status line contradicts this.

## Exit Criteria

- [ ] §2.3 uses decoded field names: constant_1, constant_0, player_index,
      viewid_stride, constant_2, block_start, block_end
- [ ] §2.3 content matches §7.1 (0x81 Player Assignment Message)
- [ ] No duplicate section numbers
- [ ] All cross-references point to correct section numbers
- [ ] Every section marked "COMPLETE" in spec-status.md has fully accurate content
- [ ] No "meanings not fully reversed" or "unknown" language for fields that
      have been decoded
- [ ] spec-status.md §2.3 status updated to "Complete"
- [ ] Spec passes a self-consistency review (no section contradicts another)

## Risks

- Low risk. This is a documentation-only change with no code impact.
- The spec is 950 lines; care needed not to introduce new errors while fixing old ones.
