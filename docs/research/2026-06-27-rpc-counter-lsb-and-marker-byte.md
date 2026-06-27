# RPC Counter LSB and Marker Byte Investigation (2026-06-27)

## Counter LSB (Bit 71)

The 16-bit counter field at bits 56–71 encodes `rpcCounter * 2` in the
upper 15 bits. Bit 71 (the LSB) varies independently of the counter value,
direction, first_use flag, method, and mode. The same counter value can
appear with different bit-71 values from the same sender.

**Conclusion:** Bit 71 is an internal Unity state flag that receivers do
not validate. Treat the counter as 15 bits (shift right by 1) and ignore
the LSB. Clean uniform increments are observed when reading the upper 15 bits.

## Marker Byte (Bits 72–79)

Previously assumed to be a constant 0x0b, the byte at position 9 (bits 72–79)
is actually a message subtype indicator:

| Value | Meaning |
|-------|---------|
| 0x0b  | User RPCs (normal RPC format with method index/hash + params) |
| 0x80  | Internal RPCs (`__RPCNetworkInstantiate` and similar) |
| 0x7f  | Delta-compressed state sync (OnSerializeNetworkView) |

All three share message ID 0x1b but have different payload formats after
the marker byte.

### Marker 0x80 Messages (Internal RPCs)

Observed in both our experiments (17 server→client messages in
InstantiateExperiment) and Distance capture (2 messages). In Distance:
- method_idx=76 and 77 with "constant"=0x65e0 and "remaining"=7171
- These nonsensical field values indicate the subsequent-use field layout
  does NOT apply to marker=0x80 messages. The payload format after the
  marker byte is different and has not been decoded.

### Marker 0x7f Messages (State Sync)

These are UNRELIABLE_SEQUENCED (reliability=1) messages carrying
OnSerializeNetworkView data. They share msg_id 0x1b with RPCs but
use a completely different payload structure. The verify script correctly
filters these out by checking reliability type.
