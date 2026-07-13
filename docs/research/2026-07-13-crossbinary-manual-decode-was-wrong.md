# CrossBinary's "0x07 = dispatch index" evidence was a manual mis-decode

## RETRACTED (2026-07-13, later same day)

**This document's central conclusion is inverted. Do not use it.** The
"re-decode" below used a `decode_batch_index` that was *itself* the
broken component (wrong bit layout — read a 5-bit field starting
immediately after the hash with no offset, then `<<2`; the real layout is
a 31-bit length field, no separate flag bit, with the true index recovered
from the frame's trailing bits: `payload[-1] & 0x7F` when the tail is 9
bits, `128 + ((payload[-1] >> 6) & 0x3) * 4` when the tail is 17 bits).
The 5-bit reconstruction below (`0b10110=22, <<2=88`) is that same bug,
reproduced by hand.

With the fixed decoder, re-running this exact pcap gives 0x07 = 96 (client
→server) / 108 (server→client) for RPC_Int — i.e. it matches each side's
real static index exactly, contradicting this doc's Result table below
(`88 / 88`) at every row. The 2026-06-28 manual analysis this doc set out
to debunk was right; this doc's own "corrected" re-decode was wrong in a
new way, not righter than the thing it was correcting.

Beyond restoring the match, a direction-resolved src/dst read of the same
pcap answers this doc's own "not settled" section: the endpoint that
announces an index via 0x07 later *receives* subsequent-use traffic at
that index (never sends at it) — confirming **adoption** (sender uses the
peer's announced index), not "0x07 is inert/method-name-keyed only." Full
corrected table and reasoning: `docs/plans/large-delta-cross-assembly-
index-test.md`'s Erratum section. Also see `[[batch-index-protocol]]`
memory (rewritten to the corrected model) and `docs/research/2026-07-13-
batch-index-decoder-was-broken.md` for the decoder fix itself.

What survives from this doc, unaffected by the retraction: the general
observation that manual/positional-log misreads have been a recurring
failure mode in this investigation (the S3/S4/S8 "silence" misreads, the
wire-format-doc 33-bit-vs-31-bit mismatch) — the lesson to always
verify a decoder positionally against raw bytes rather than trusting any
single read, including this doc's own, still stands.

The rest of this document is kept verbatim below for the historical
record of how the error occurred; treat every technical claim in it as
**false** unless cross-checked against the corrected sources above.

---

**Context.** The user asked whether the pre-07-12 "both sides learn the
subsequent-use index via 0x07" model might actually have been correct, with
some other bug misattributed to it — since both first-use (tag collisions)
and subsequent-use dispatch showed problems across the investigation. An
Explore/general-purpose agent was tasked with cataloging every experiment
and belief-revision in the session transcript to find the strongest evidence
on either side.

That catalog identified `captures/CrossBinary-20260628-004945.pcap` (2026-06-28)
as the single strongest piece of evidence FOR the dynamic-learning model: two
real Unity builds (one patched with 3 extra `[RPC]` methods, a known +12
static-index shift) exchanged RPCs, and the 2026-06-28 manual hex analysis
reported the 0x07 batch-index value matching each side's subsequent-use index
for all 4 methods tested (RPC_Int, RPC_Float, RPC_String, RPC_Alpha). This was
the origin of the "Unity DOES learn!" conclusion, later reversed by the
07-12 "decoupled" model — but the reversal's own falsifying evidence (from a
*different*, pre-InheritedRpc assembly, decoded by a decoder that had gone
through two bit-layout bug fixes since) was itself confound-laden. Both sides
of the question rested on shaky ground, so this pcap was re-decoded from
scratch with the current, code-accurate bit layout
(`protocol/unity_protocol.py:decode_batch_index`) rather than by hand.

## Result: 0x07 does not match either side's real static index, for any method

| Method | 0x07 (client→server / server→client) | Real subsequent-use index used (server / client) | Delta between real indices |
|---|---|---|---|
| RPC_Int | 88 / 88 | 96 / 108 | 12 |
| RPC_Float | 120 / 124 | 100 / 112 | 12 |
| RPC_String | 24 / 28 | 104 / 116 | 12 |
| RPC_Alpha | 32 / 32 | 132 / 5 (see caveat) | — |

The real subsequent-use indices (from actual `rpc` subsequent-use packets,
not `batch_index` packets) reproduce the known +12 static-index shift
between the two builds exactly, for Int/Float/String. The 0x07 values do
not match either build's real index for any method, and don't even
reproduce a clean +12 (or any other consistent) delta between the two
sides — RPC_Int's 0x07 is identical on both sides (88/88, delta 0),
RPC_Float and RPC_String's 0x07 differ by 4 between sides (not 12), and
RPC_Alpha's is identical again (32/32).

(RPC_Alpha's real subsequent-use index of 5 for the client side is
almost certainly itself a decode artifact of the ≥128-header case — Alpha's
real index should be ~132+12=144, which needs the extended header format;
not fully investigated here, doesn't change the conclusion since even the
32/32 batch-index pair alone rules out a match.)

## Why the original manual analysis got this wrong

The batch-index message layout is: `msg_id(8) + length_field(31, "quarter
bits") + class_guid(48) + method_hash(variable) + method_index(5, <<2) +
padding`. None of these fields are byte-aligned relative to each other in
general (e.g. for RPC_Int: 8+31+48+16=103 bits before the index field, so
the 5-bit index spans bits 103-107, straddling byte 12/13's boundary).

The 2026-06-28 manual analysis appears to have read the raw trailing byte
of each frame directly as if it were the index (e.g. RPC_Int's two frames
end in `...a8ad60` and `...a8ad6c` — reading `0x60`=96 and `0x6c`=108
literally lines up suspiciously well with the two builds' real indices).
But a correct bitstream walk shows both frames decode to the *same* 5-bit
field (`0b10110`=22, `<<2`=88) — the differing trailing nibble is in the
4 unconsumed padding bits *after* the index field, not part of it at all.
This is now the fourth documented instance in this investigation of a
conclusion built on a byte/log misread rather than a positional decode,
alongside the S3/S4/S8 "silence" misreads and the wire-format-doc/code
33-bit-vs-31-bit length field mismatch (see `2026-07-13-subsequent-use-
static-index-dispatch.md` erratum and `unity-legacy-networking-wire-
format.md` §3.8.1, which still needs a matching correction — tracked
below).

## What this settles, and what it doesn't

**Settled:** the currently-documented "decoupled" model
([[batch-index-protocol]]) holds up under a from-scratch, code-accurate
re-decode of the single strongest real Unity↔Unity cross-build capture in
the dataset. The pre-07-12 "dynamic learning via 0x07" model was based on
a manual-decode error, not on a real signal that was later misattributed.
Re-deriving indices from 0x07 is not a viable path forward; per CLAUDE.md,
per-build empirical extraction or an out-of-band shared index table remains
the way to bridge two differing assemblies.

**Not settled:** whatever 0x07 actually encodes remains unknown (its
values here are internally consistent — deterministic, and for
Int/Alpha identical across sender identity — but don't correlate with
any known per-method or per-build quantity we've tried). Also not
settled: whether real shipped Unity games ever actually run client and
dedicated server from *genuinely* different assemblies in production, or
whether that's a purely synthetic scenario this repo's test harness
introduced (the CrossBinary experiment's +12 delta was itself an
artificial patch, not observed from any real two-build game pairing).
This second question directly motivates testing with a much larger,
naturally-arising method-count delta between two independently-built
assemblies (see task #18 / CLAUDE.md's two-assembly testing convention).

## Follow-up needed

- `unity-legacy-networking-wire-format.md` §3.8.1 still documents the
  stale pre-881f335 (33-bit) length field for the 0x07 message; needs
  the same correction already applied to the decoder and to this doc.
- Beta/Gamma slot puzzle (existing, see [[batch-index-protocol]]) and
  the ≥128 header behavior in 0x07 frames specifically (Alpha's frame
  here had 12 unconsumed trailing bits vs. 4 for the other three methods
  at the same hash length — consistent with the known-open "0x07's index
  field may have a wider variable structure" question) remain open;
  not chased further here since they don't bear on the central question.
