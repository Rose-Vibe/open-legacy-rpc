# M21: Independent Protocol Verification Experiments

## Goal

Independently verify each M20 protocol fix by capturing real Unity wire traffic
and comparing to our encoder output. The protocol format must be derivable from
experiments in this repo, not just trusted from the distance-server session.

## Fixes to Verify

| Fix | What | How to Observe |
|-----|------|----------------|
| 1 | USER_RPC_CONSTANT = 0x2000 | Any user RPC capture, extract 16-bit constant field |
| 2 | 16-bit counter | Send >128 RPCs, verify counter doesn't wrap at 128 |
| 3 | Subsequent remaining = total_bits - 120 | Capture subsequent RPC, compute remaining vs frame size |
| 4 | First-use remaining = param_bits + 20 | Capture first-use RPC, compute remaining vs param size |
| 5 | method_tag in first-use | Capture first-use for multiple methods, read 4-bit tag field |
| 6 | bitLength in RakNet frame | Check frame bitLength field matches RPC bit count |
| 7 | Disconnect 0x13 vs 0x15 | Capture disconnect, observe msg ID (expect 0x15 for Unity 2018) |

Note: Fix 7 (0x13) can only be verified with a Unity 5.5 build. Our Unity 2018.1.6f1
build will produce 0x15. We document this and confirm 0x15 from capture.

## New Experiments

### HighCounterExperiment
Sends 200 sequential RPC_Int calls from client to server, with values 0-199.
Purpose: verify counter values above 128 appear in the wire format.

### (Reuse existing experiments)
- **RpcIntExperiment**: captures subsequent-use RPCs for Fix 1, 3, 6
- **RpcNameVaryExperiment**: captures first-use RPCs for Fix 4, 5
- **DisconnectCleanupExperiment**: captures disconnect for Fix 7

## Verification Script

`scripts/verify-protocol-fields.py` — parses pcap files and extracts:

1. RakNet datagram → encapsulated frames → Unity RPC payloads
2. For each RPC payload, extract and report:
   - Counter value (byte 7-8 decoded as 16-bit)
   - Whether first-use or subsequent
   - USER_RPC_CONSTANT value
   - Remaining bit count
   - Method tag (first-use only)
   - RakNet frame bitLength vs payload byte count
3. For disconnect: report the msg_id byte
4. Compare all extracted values against our Python encoder output for the same
   method/params/counter combination
5. Print PASS/FAIL per check

## Exit Criteria

1. HighCounterExperiment runs and pcap captured
2. Verification script extracts fields from all three pcaps
3. Each fix maps to at least one PASS assertion from real wire data
4. Results documented in `docs/research/`
