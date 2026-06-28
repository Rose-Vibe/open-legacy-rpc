# PCAP Decoder Tool

## Goal

Build a Python CLI tool that reads a pcap/pcapng file and outputs structured
JSON decoding every packet through the full stack: RakNet → Unity → game-specific.

Every layer includes both the raw data and the decoded interpretation. The output
uses discriminated unions so consumers can pattern-match on packet/frame/message
types. Game-specific payloads that can't be decoded are emitted as
`{ "type": "not_deserialized", "rawHex": "..." }` — a clear marker for
downstream post-processing.

## Input

A single JSON config object, all fields optional. Read from `--config <file>`
or stdin (when no `--config` given and stdin is not a tty).

```json
{
  "serverPort": 7777,
  "methodSignatures": {
    "RPC_TakeDamage": ["int", "float"],
    "RPC_Heal": ["int"]
  },
  "viewNames": {
    "8192": "Player"
  }
}
```

- `serverPort` — determines packet direction (`client_to_server` /
  `server_to_client`). Default: `null` → direction is `"unknown"`.
- `methodSignatures` — maps method names to parameter type lists. Methods not
  listed here produce `not_deserialized` params. Built-in signatures from
  `METHOD_SIGNATURES` are always available.
- `viewNames` — optional human-readable names for view IDs, included as
  metadata when a matching view_id appears.

## Output Schema

Top-level: `{ "packets": [...] }` written to stdout as JSON. Pretty-printed
by default, `--compact` for single-line output.

### Packet (one per UDP datagram)

```
Packet = {
  index: int,
  timestamp: float,
  direction: "client_to_server" | "server_to_client" | "unknown",
  srcPort: int,
  dstPort: int,
  rawHex: string,
  raknet: RakNetLayer
}
```

### RakNet Layer (discriminated on `type`)

The `bAndAs` field is extracted directly from the raw datagram bytes (offset
1-4), since `parse_datagram()` discards it. The tool reads it from the raw
payload before calling `parse_datagram()`.

```
RakNetLayer =
  | { type: "datagram", rawHex, bAndAs: int, timestamp: int,
      sequenceNumber: int, frames: [RakNetFrame] }
  | { type: "ack", rawHex, timestamp: int, ranges: [[min, max], ...] }
  | { type: "nak", rawHex, timestamp: int, ranges: [[min, max], ...] }
  | { type: "offline", rawHex, messageId: int }
  | { type: "unknown", rawHex }
```

### RakNet Frame (one encapsulated message)

```
RakNetFrame = {
  rawHex: string,
  bitLength: int,
  reliability: string,        // e.g. "RELIABLE_ORDERED"
  reliableMsgNumber: int | null,
  orderingChannel: int | null,
  orderingIndex: int | null,
  split: null | { count: int, id: int, index: int },
  unity: UnityLayer | null    // null for split fragments
}
```

`unity` is `null` when the frame is a split fragment that hasn't been
reassembled (we don't do reassembly in the decoder — each frame is decoded
independently; split payloads are partial and can't be decoded).

### Unity Layer (discriminated on `type`)

```
UnityLayer =
  | { type: "rpc", rawHex, msgId: 0x1b, ...RpcFields }
  | { type: "state_sync", rawHex, msgId: 0x1b, ...StateSyncFields }
  | { type: "batch_index", rawHex, msgId: 0x07, ...BatchFields }
  | { type: "connection", rawHex, msgId: int, messageName: string }
  | { type: "master_server", rawHex, msgId: int, messageName: string, ...MasterFields }
  | { type: "unknown", rawHex, msgId: int }
```

#### RPC Fields

`decode_rpc()` omits the `params` key when the method signature is unknown.
The wrapper detects this and emits the remaining payload as a single
`not_deserialized` param entry.

For subsequent-use RPCs, `methodIndex` is included so downstream can correlate
with batch_index messages.

```
RpcFields = {
  variant: "first_use" | "subsequent_use",
  viewId: int,
  rpcCounter: int,
  rpcMode: string,
  methodName: string | null,   // null if hash unknown
  targetView: int,
  // subsequent_use only:
  methodIndex?: int,
  // first_use only:
  classGuid?: string,
  methodHash?: string,
  // params:
  params: [ParamValue]
}

ParamValue =
  | { type: "deserialized", paramType: string, value: any }
  | { type: "not_deserialized", rawHex: string }
```

#### State Sync Fields

```
StateSyncFields = {
  viewId: int,
  viewIdScope: string,
  timestamp: int,
  isFirst: bool,
  data: { type: "not_deserialized", rawHex: string }
       // post-processing replaces with { type: "deserialized", ... }
}
```

#### Batch Index Fields

```
BatchFields = {
  methodName: string | null,
  methodIndex: int
}
```

#### Connection Fields

Known connection message IDs:
- 0x00 INTERNAL_PING
- 0x03 CONNECTED_PONG
- 0x04 CONNECTION_REQUEST
- 0x09 OPEN_CONNECTION_REQUEST
- 0x0A OPEN_CONNECTION_REPLY
- 0x0E CONNECTION_REQUEST_ACCEPTED
- 0x11 NEW_INCOMING_CONNECTION
- 0x13 DISCONNECTION_NOTIFICATION_LEGACY
- 0x15 DISCONNECTION_NOTIFICATION
- 0x17 CONNECTION_BANNED
- 0x81 UNITY_PLAYER_ASSIGNMENT
- 0x83 UNITY_PLAYER_READY

These are identified by msg_id but not deeply decoded (they have varying
formats). The `messageName` field provides the human-readable name.

#### Master Server Fields

Identified by msg_id 75-80, 200-202. Decoded using `master_serialization.py`
when the payload is valid.

## Implementation

Single file: `tools/decode_pcap.py`. Executable as
`python3 tools/decode_pcap.py <pcap_file> [--config <config_file>] [--compact]`.

Dependencies: only the existing `protocol/` modules and stdlib.

### Structure

1. **`main()`** — CLI arg parsing, config loading, pcap reading, JSON output
2. **`decode_packet()`** — UDP payload → full nested dict
3. **`decode_raknet()`** — parses `bAndAs` from raw bytes, calls `parse_datagram()`,
   dispatches to datagram/ack/nak/offline/unknown builders
4. **`decode_frame()`** — single RakNetMessage → frame dict with unity layer
5. **`decode_unity()`** — msg_id dispatch → Unity layer dict
6. **`decode_rpc_layer()`** — wraps `decode_rpc()`, handles missing params (emits
   remaining bytes as `not_deserialized`), merges config method signatures
7. **`decode_state_sync_layer()`** — wraps `decode_state_sync()`, emits data as
   `not_deserialized`
8. **`decode_batch_index_layer()`** — wraps `decode_batch_index()`
9. **`decode_connection_message()`** — msg_id → name lookup table
10. **`decode_master_server_message()`** — wraps `master_serialization` decoders

### Config loading

```
if --config given:
    read JSON from file
elif stdin is not a tty:
    read JSON from stdin
else:
    empty config (all defaults)
```

### Implementation notes

- `parse_datagram()` discards `bAndAs` — the tool reads it directly from
  `payload[1:5]` before calling `parse_datagram()`.
- `decode_rpc()` does not return a `method_index` field for subsequent-use RPCs
  — the tool reads it from `payload[10]` (byte position of the method_idx field
  after the marker byte) to include in the output.
- `decode_rpc()` omits `params` when the signature is unknown — the wrapper
  computes the remaining bytes after the mode field and emits them as a single
  `not_deserialized` entry.
- `decode_instantiate_params()` exists for `__RPCNetworkInstantiate` but is not
  wired up in v1. It would appear as `not_deserialized` params. Future enhancement.

## Exit Criteria

1. Decodes all packet types in a real Unity pcap (datagram, ACK, NAK, offline)
2. RPC params decoded when signatures available, `not_deserialized` otherwise
3. State sync data always `not_deserialized` (game-specific)
4. BATCH index messages decoded
5. Connection messages identified by name
6. Every node includes `rawHex` of its layer's bytes
7. Output is valid JSON matching the schema above
8. Tests cover each packet type variant and the config loading
