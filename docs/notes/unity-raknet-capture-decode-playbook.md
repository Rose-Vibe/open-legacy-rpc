# Observing & Reverse-Engineering Unity Legacy Networking (RakNet) on the Wire

A capture-and-decode playbook for understanding the wire protocol between two Unity projects (a server and a client you write yourself) that use Unity's **legacy** networking — `NetworkView` / `[RPC]` / `OnSerializeNetworkView` / `NetworkViewID`.

## Goal & context

Unity's legacy networking rides on **RakNet 3.731** (wire-compatible with 3.732). The RakNet transport is open source; what is *not* documented anywhere is **Unity's framing on top of RakNet** — the RPC name→identifier scheme, NetworkViewID encoding, the `OnSerializeNetworkView` state layout, and the instantiate/buffering/group messages. Recovering that framing is the objective (it feeds an eventual Unity-less reimplementation of the protocol).

Big advantage: **you control both endpoints.** Write a minimal Unity server + client, drive them deliberately, and observe. That turns this from "sniff a black box" into controlled experiments.

## The traffic — two things to set up first

1. **It's UDP.** RakNet is UDP with its own reliability layer on top. Use UDP-capable tooling — not TCP/HTTP proxies.
2. **Disable encryption.** Do **not** call `Network.InitializeSecurity()` on the server; that enables RakNet's encryption and you'll capture ciphertext. Leave it off so payloads are plaintext (RakNet's binary format, but readable).
3. **Run both projects on one host** and capture loopback (`lo`). Simplest possible setup, no second machine.

## Capture — two complementary approaches; use both

### A. Passive capture (ground truth): `tshark` on loopback
Misses nothing, produces a replayable pcap, structured output for parsing.

```bash
# capture UDP on loopback to a pcap (narrow to your port once you know it)
sudo tshark -i lo -f "udp" -w /tmp/unity.pcap

# inspect: structured JSON, or raw hex per packet
tshark -r /tmp/unity.pcap -T json
tshark -r /tmp/unity.pcap -x

# force Wireshark's built-in RakNet dissector onto your port
# (recognizes the connection HANDSHAKE only — not Unity's connected framing)
tshark -r /tmp/unity.pcap -d udp.port==7777,raknet -V
```

So you don't need root every run, grant `dumpcap` the capability once:
```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(which dumpcap)
```
`tcpdump -i lo -w …` is a lighter alternative. `editcap` / `mergecap` slice and combine pcaps into reproducible test cases.

### B. Active capture (cleanest logs): a tiny UDP relay you write
Because you own both ends, point the **client** at a local proxy that forwards to the **server** and logs every datagram with direction + timestamp + hexdump. ~40 lines of Python (one upstream socket per client; `recvfrom`/`sendto`; log both directions). Directional, per-datagram, immediately readable, no privileges, ideal for the differential experiments below.

Caveat: RakNet's handshake echoes back the address it sees, so on rare configs it may reject the proxied source. If the connection won't establish through the proxy, fall back to passive `tshark` (always correct). Recommended: run the proxy for fast readable iteration **and** keep a pcap as the authoritative record.

## Decode — turning bytes into Unity's framing

**Don't reverse-engineer the transport** — use the open **RakNet 3.731/3.732 source** as the spec for the datagram + reliability layer (`ReliabilityLayer`, `RakPeer`). Pipeline:

```
UDP payload
  → parse RakNet datagram header (sequence #, per-message reliability/ordering headers, split-packet flags)
    → encapsulated message
      → first byte is the message ID
         - low IDs  = RakNet system messages (handshake, ACKs, etc.)
         - >= ID_USER_PACKET_ENUM = Unity's payload  ← THIS is the target layer
```

The user-message payload is where RPC dispatch, `NetworkViewID`, and `OnSerializeNetworkView` state live.

Two ways to build the Unity-layer parser:
- **Iterative decoder script** — Python with `scapy` (`rdpcap`), `dpkt`, or `pyshark` (wraps tshark's dissection). Read the pcap, extract UDP payloads, parse field by field, refine.
- **Wireshark Lua dissector** (`tshark -X lua_script:unity_raknet.lua`) — more durable: the dissector *becomes* the protocol documentation and runs headlessly in tshark. Develop and unit-test it without Wireshark using **WireBait** (runs dissectors against hex strings / pcap files). Mika's "Creating a Wireshark dissector in Lua" series is the canonical tutorial.

## The method that actually cracks it — differential analysis

The tooling is secondary to the technique, and the technique works *only* because you write both apps:

- **Start silent.** Connect and send nothing, to isolate the handshake bytes. Then add exactly one behavior at a time.
- **One RPC, then diff.** Fire a single RPC in isolation (e.g. `networkView.RPC("Foo", RPCMode.Server, 42)`), find its bytes. Then change one thing — the method name, then one parameter value, then its type — and **diff** the captured output. The deltas reveal the RPC name-hash scheme, the NetworkViewID encoding, and the per-type serialization, one variable at a time.
- **Correlate with logs.** Instrument both Unity sides with `Debug.Log` (RPC name, params, view ID, `Time.realtimeSinceStartup`) and match to packets by timestamp, so every datagram has a known cause.

Keep every pcap — they're deterministic artifacts to re-run against as the dissector/parser improves.

## Setup

```bash
sudo apt install -y tshark tcpdump
pip install scapy pyshark dpkt
# plus: clone the RakNet source for the datagram-layer reference
#       (facebookarchive/RakNet — version 3.731/3.732 semantics)
```

The UDP proxy and the Lua dissector are things to write and iterate on — both squarely in scope for a coding agent.