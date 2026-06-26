# M2: Reference Spec & Python Implementation

## Goal

Produce a complete reference specification of Unity's legacy networking wire
format and build a Python reference implementation (client and server) that
can interoperate with a Unity 2018.1.6f1 headless player.

## Why

The decoded wire format knowledge is currently scattered across Python
analysis scripts and session notes. Consolidating it into a formal spec
makes the protocol portable to any language. The Python implementation
proves the spec is correct by demonstrating bidirectional communication
with a real Unity endpoint.

---

## Phase 1: Reference Specification

Write `docs/research/unity-legacy-networking-wire-format.md` covering:

### 1.1 Transport: RakNet 3.731

- UDP datagram structure (flags, B/AS, timestamp, sequence number)
- ACK/NAK ranges
- Encapsulated message header (reliability, bit_length, reliable_msg_number,
  ordering_index, ordering_channel, split packets)
- Reliability levels and their field sets
- IP address encoding (bitwise-inverted)

### 1.2 Connection Handshake

Standard RakNet messages:
- `0x04` ID_CONNECTION_REQUEST
- `0x0e` ID_CONNECTION_REQUEST_ACCEPTED (address layout)
- `0x11` ID_NEW_INCOMING_CONNECTION (address layout)

Unity-specific messages:
- `0x83` client→server player ready (5 bytes)
- `0x81` server→client player assignment (29 bytes, 7× uint32)

Plus RakNet internal ping/pong (0x00, 0x03).

### 1.3 RPC Wire Format (msg_id 0x1b, RELIABLE_ORDERED)

- Header: msg_id + 48-bit ViewID + 24-bit invocation metadata
- First-use vs. subsequent encoding with exact bit-offset tables
  (document the variable-length method hash section and how it shifts
  downstream fields; explain magic offsets like `length_indicator_pos = 13*8`)
- Method name hashing: class GUID (0c93b276d5b1) + method hash;
  document all observed hash values and note that the hash algorithm
  itself has not been reversed
- Method index caching (7-bit index, subsequent-use format)
- RPCMode encoding (4 bits)
- Parameter encoding per type (int, float, string, Vector3, Quaternion, byte[])
- WriteCompressed<uint32> algorithm (half-byte optimization)
- Huffman string encoding (RakNet StringCompressor with englishCharacterFrequencies)

### 1.4 State Sync Wire Format (msg_id 0x1b, UNRELIABLE_SEQUENCED)

- 12-byte header (msg_id + ViewID + timestamp + flags + constant 0x0004)
- Data bit count = bit_length - 96
- BitStream.Serialize type encoding (int, float, Vector3, Quaternion,
  bool, short, char) — sizes, endianness, no alignment padding

### 1.5 Offline Messages

- RakNet offline message magic
- Open connection request/reply sequences

### Exit Criteria

- Spec covers all observed message types
- Each field has bit offset, size, endianness, and encoding documented
- Spec includes worked examples from actual captures

---

## Phase 2: Python Reference Implementation

The `protocol/` directory already contains analysis scripts (`analyze_pcap.py`,
`diff_experiment.py`, `pcap_reader.py`, `huffman.py`, `raknet.py`,
`unity_rpc_decode.py`). The reference implementation builds on top of these,
adding new modules alongside them. Add `protocol/__init__.py` to make it a
proper Python package. Update existing modules to use package-relative imports
(replace `sys.path.insert` hacks).

### 2.1 BitStream (`protocol/bitstream.py`)

Read/write bit-level operations. Supports:
- Read/write: bits, u8, u16_be, u32_be, i32_be, float_be
- Read/write: bool (1 bit), short (16-bit signed BE), char (8-bit)
- WriteCompressed<uint32> (read and write)
- Byte-aligned reads/writes
- Position tracking, remaining bits

Refactored from the existing `BitReader` in `unity_rpc_decode.py`, extended
with write support. Preserves the existing `huffman.py` module as a dependency
for string encoding/decoding — do not reimplement it.

### 2.2 RakNet Transport (`protocol/raknet_transport.py`)

Low-level UDP socket operations:
- `RakNetPeer` class: manages a UDP socket, datagram sequencing, timestamps
- Send/receive datagrams with proper header format
- ACK generation and processing
- Reliability layer: reliable message numbering, ordering
- Encapsulated message framing (pack and unpack)
- Split packet reassembly: buffer fragments keyed by `split_packet_id`,
  reassemble when all `split_packet_count` fragments arrive, ordered by
  `split_packet_index`. Required for large RPCs (string/byte[] params
  exceeding ~1200 byte MTU).

### 2.3 RakNet Connection (`protocol/raknet_connection.py`)

Connection lifecycle:
- Offline message exchange (open connection request/reply)
- Connection handshake (0x04, 0x0e, 0x11)
- Ping/pong (0x00, 0x03)
- Disconnect handling
- State machine: DISCONNECTED → CONNECTING → CONNECTED → DISCONNECTED

### 2.4 Unity Protocol (`protocol/unity_protocol.py`)

Unity-layer message encoding/decoding:
- RPC encode/decode (first-use and subsequent formats)
- State sync encode/decode
- Unity connection messages (0x81 player assignment, 0x83 player ready)
- Player index tracking: server assigns indices, client stores its own
- NetworkViewID encoding
- Method hash table (observed hashes; document that algorithm is not reversed)

### 2.5 Unity Client (`protocol/unity_client.py`)

High-level client API:
```python
client = UnityClient()
client.connect("127.0.0.1", 7777)
client.send_rpc("RPC_Int", [42], view_id=1, mode=RPCMode.Server)
client.on_rpc("RPC_String", lambda s: print(s))
client.on_state_sync(view_id=1, callback=handle_sync)
client.disconnect()
```

The client must parse the 0x81 player assignment to know its own player
index, and send 0x83 during connection setup.

### 2.6 Unity Server (`protocol/unity_server.py`)

High-level server API:
```python
server = UnityServer(port=7777, tick_rate=15)
server.on_client_connected(lambda player: ...)
server.on_rpc("RPC_Int", lambda player, val: ...)
server.send_rpc("RPC_Int", [42], target=player, mode=RPCMode.All)
server.send_state_sync(view_id=1, data=...)
```

The server runs a `select()`-based poll loop at configurable tick rate
(default 15 Hz, matching Unity's default `Network.sendRate`). The server
assigns player indices and sends 0x81 to connecting clients.

### Exit Criteria

- All modules have unit tests for encode/decode round-trips
- BitStream write produces bytes that the existing decoder can read
- RPC encode matches wire captures
- State sync encode matches wire captures

---

## Phase 3: Integration Testing

### 3.1 Python Client → Unity Server

1. Start Unity server (headless, network namespace)
2. Python client connects from the same namespace
3. Python client sends RPCs to Unity server
4. Verify Unity server receives and logs the RPC values correctly
5. Unity server sends RPCs back to Python client
6. Verify Python client receives correct values

### 3.2 Python Server → Unity Client

1. Start Python server (in network namespace)
2. Unity client connects to Python server
3. Unity client sends RPCs to Python server
4. Verify Python server receives correct values
5. Python server sends RPCs back to Unity client
6. Verify Unity client receives correct values

### 3.3 State Sync

1. Unity server with state sync → Python client receives and decodes
2. Python server with state sync → Unity client receives and applies

### Exit Criteria

- Python client can connect to Unity server, exchange RPCs, disconnect cleanly
- Python server can accept Unity client, exchange RPCs, disconnect cleanly
- State sync works in both directions
- Reliable message retransmission works (verify by checking ACK processing)
- All integration tests pass without manual intervention

---

## Implementation Order

Phase 1 (spec), Phase 2.1 (BitStream), and Phase 2.2 (RakNet Transport)
can proceed in parallel — RakNet's wire format is well-understood from the
open-source code and existing `raknet.py` parser.

Phase 2.3-2.4 depend on the spec being finalized for Unity-layer details.
Phase 2.5-2.6 depend on 2.2-2.4.
Phase 3 depends on Phase 2 being complete.

Within Phase 2, build bottom-up: BitStream → RakNet Transport → RakNet
Connection → Unity Protocol → Client/Server.

## Decisions

- **No asyncio**: Use blocking sockets with `select()` for the reference
  implementation. Simpler to debug and matches the single-threaded Unity
  networking model.
- **No encryption**: Matches the Unity side (no `InitializeSecurity()`).
- **Method hash table**: Use the observed hash table rather than trying to
  reverse-engineer the hash algorithm. Add new entries as needed.
- **Python 3.8+**: Use f-strings, dataclasses, typing. No external
  dependencies beyond the standard library.
