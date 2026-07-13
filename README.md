# open-legacy-rpc

Reverse-engineered wire format spec and implementations (Python + TypeScript)
of Unity's legacy RPC networking stack (`NetworkView` / `[RPC]` /
`OnSerializeNetworkView`), last supported in Unity 2018.1.6f1. The transport
layer is RakNet 3.731; this project documents and implements **Unity's
undocumented framing on top of RakNet**.

Unity is a trademark of Unity Technologies. This project is independent,
clean-room reverse-engineered, and not affiliated with or endorsed by Unity
Technologies.

## Repository Structure

```
protocol/       Python reference implementation (client + server)
ts/             TypeScript production implementation (client + server)
experiments/    Unity projects for capture-based protocol analysis
docs/research/  Wire format specifications
docs/notes/     Lab notes and setup guides
docs/plans/     Sprint plans (active and archived)
```

## Prerequisites

- **Python**: 3.10+
- **Node.js**: 18+ (TypeScript implementation)

## Quick Start

### Python

```bash
cd protocol
pip install -e .          # or: pip install -r ../requirements-dev.txt
python -m pytest ../tests/
```

### TypeScript

```bash
cd ts
npm install
npm test
```

## Wire Format Specs

- [Unity Legacy Networking Wire Format](docs/research/unity-legacy-networking-wire-format.md)
- [Master Server Wire Format](docs/research/master-server-wire-format.md)
- [Spec Status](docs/research/spec-status.md)

## Usage

### TypeScript Server

```typescript
import { UnityServer, createUdpSocket } from 'open-legacy-rpc';

const socket = createUdpSocket();
const server = new UnityServer(socket, { port: 7777 });

server.onConnect((session) => {
  console.log(`Client connected: ${session.id}`);
});

server.onRpc('MyRpc', (session, ...params) => {
  console.log('RPC received:', params);
});

await server.start();
```

### Python Client

```python
from protocol.unity_client import UnityClient

client = UnityClient()
client.connect('127.0.0.1', 7777)

client.send_rpc('MyRpc', [42], view_id=1)

for msg in client.poll(timeout=1.0):
    print(msg)

client.disconnect()
```

## PCAP Decoder

Decode pcap/pcapng captures into structured JSON through the full protocol
stack (RakNet → Unity → game-specific):

```bash
python3 tools/decode_pcap.py capture.pcap                       # all defaults
python3 tools/decode_pcap.py capture.pcap --config config.json   # with config
python3 tools/decode_pcap.py capture.pcap --compact              # single-line JSON
```

Config file (all fields optional):

```json
{
  "serverPort": 7777,
  "methodSignatures": { "RPC_TakeDamage": ["int", "float"] },
  "viewNames": { "8192": "Player" }
}
```

Output uses discriminated unions at each layer (`type` field). Game-specific
data that can't be decoded is marked `{ "type": "not_deserialized", "rawHex": "..." }`
for downstream post-processing.

## Network Namespace

Unity's RakNet crashes when the host has >10 IPv4 addresses. Use the
included scripts to create an isolated network namespace:

```bash
sudo bash netns-setup.sh                          # create namespace
sudo ip netns exec unitynet ./Player.x86_64 ...   # run Unity inside
tshark -i veth-unet-h -f 'udp' -w /tmp/unity.pcap   # capture from host
sudo bash netns-teardown.sh                        # clean up
```

## Shell Scripts

| Script | Purpose |
|--------|---------|
| `run-experiment.sh` | Run a Unity experiment with traffic capture |
| `run-interop-tests.sh` | End-to-end interop tests: Python <-> Unity |
| `run-server-only.sh` | Start a Unity server, wait for external connections |
| `netns-setup.sh` | Create network namespace for Unity |
| `netns-teardown.sh` | Tear down network namespace |
