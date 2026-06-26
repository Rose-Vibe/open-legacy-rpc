# M1: Experiment Harness & First Captures

## Goal

Stand up a single Unity 2018.1.6f1 project that acts as a thin networking
shell, driven by an external DLL that defines experiments. Verify it builds,
runs server and client inside the network namespace, and produces usable
pcap captures. Then build out the experiment framework and run the first
connection-handshake capture.

## Why

Everything downstream (differential analysis, protocol decoding, Lua
dissector, eventual reimplementation) depends on having a reliable,
repeatable way to generate targeted network traffic and capture it. Getting
this right first means every future experiment is just "write a new class,
rebuild the DLL, run the script."

---

## Phase 1: Unity Loader Project

### What to build

A single Unity project (`UnityProject/`) with one scene containing one
GameObject with a `Loader` MonoBehaviour. The Loader:

1. Parses command-line args to determine:
   - **Role**: `--server` or `--client`
   - **Experiment**: `--experiment <name>` (class name in the external DLL)
   - **Server address/port** for client mode (defaults to `127.0.0.1:7777`)
2. Loads the external experiment DLL from a known path
   (e.g. `Experiments/Experiments.dll` next to the player binary)
3. Uses reflection to find and instantiate the named experiment class
4. Calls an `IExperiment` interface on it:
   - `void Setup(ExperimentContext ctx)` — called before networking starts;
     the context provides the role, parsed args, and a logging callback
   - `void OnServerReady()` / `void OnClientConnected()` — called from
     Unity's `OnServerInitialized` / `OnConnectedToServer`
   - `void OnPlayerConnected(NetworkPlayer player)` /
     `void OnPlayerDisconnected(NetworkPlayer player)`
   - `void Tick()` — called every `Update()`, for experiments that need
     to do timed sequences
   - `void Shutdown()` — cleanup
5. The Loader itself handles `Network.InitializeServer()` /
   `Network.Connect()` based on the role, and wires Unity's networking
   callbacks to the experiment interface.
6. **Must NOT call `Network.InitializeSecurity()`** — that enables
   RakNet encryption and we'd capture ciphertext instead of plaintext.

### What NOT to put in the Unity project

- Any experiment-specific logic
- Any RPC methods beyond a universal forwarding shim (see below)
- `Network.InitializeSecurity()` — ever

### The RPC forwarding problem

Unity's `[RPC]` methods must be compiled into the assembly that the
`NetworkView` component lives on. We can't define `[RPC]` methods in the
external DLL and have Unity's networking find them. Options:

- **Option A: Pre-declare a set of generic RPCs** in the Loader script
  (`RPC_0(byte[] data)`, `RPC_1(byte[] data)`, etc.) that forward to the
  experiment. The experiment chooses which slot to use. Pragmatic but means
  every RPC has the same wire signature (`byte[]`), which limits what we
  learn about per-type serialization.
- **Option B: Pre-declare RPCs with varied signatures** — a matrix of
  methods covering the type combinations we care about:
  `RPC_Int(int a)`, `RPC_String(string s)`, `RPC_IntFloat(int a, float b)`,
  `RPC_Vector3(Vector3 v)`, `RPC_Bytes(byte[] data)`, etc. More methods in
  the Unity project, but each one exercises a different serialization path
  on the wire — which is exactly what we're trying to observe.
- **Option C: Generate the RPCs.** A pre-build script reads experiment
  metadata and emits C# RPC stubs into the Unity project before building.
  Most flexible but adds build complexity.

**Recommendation: Option B.** We'll need a finite set of type-varied RPCs
anyway for the differential experiments. Declare them upfront in the Loader,
document what each one is for. If we later need an RPC shape we didn't
anticipate, we add one method and rebuild — but we should rarely need to.

The same applies to `OnSerializeNetworkView` — the Loader starts with one
`NetworkView` with a serialization callback that delegates to the experiment.
The `ExperimentContext` exposes a method to create additional NetworkViews on
demand (needed for `viewid` experiments), so experiments that need multiple
views can request them without changes to the Unity project.

### Exit criteria

- `UnityProject/` opens in Unity 2018.1.6f1 without errors
- `Assets/Scripts/Loader.cs` compiles, implements the above
- `Assets/Scripts/IExperiment.cs` defines the interface (this file is
  also referenced by the external DLL project)
- A build script (`Assets/Editor/BuildScript.cs`) produces a Linux headless
  player at `Builds/Linux/Player.x86_64`

---

## Phase 2: Build & Smoke Test

### Steps

1. Create the Unity project via the editor in batchmode:
   ```bash
   xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity -batchmode -nographics \
     -createProject /home/server-mint/unity-legacy-networking-reversed/UnityProject \
     -quit -logFile -
   ```
2. Copy in the scripts (`Loader.cs`, `IExperiment.cs`,
   `Editor/BuildScript.cs`)
3. Build the player:
   ```bash
   xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity -batchmode -nographics \
     -projectPath .../UnityProject \
     -executeMethod BuildScript.BuildLinuxPlayer \
     -accept-apiupdate -quit -logFile -
   ```
4. Set up the network namespace: `sudo bash netns-setup.sh`
5. Run the player in server mode inside the namespace:
   ```bash
   sudo ip netns exec unitynet ./Builds/Linux/Player.x86_64 \
     -batchmode -nographics -logFile /dev/stdout -- --server
   ```
6. Verify it starts, `Network.InitializeServer()` binds successfully,
   `OnServerInitialized` fires, and the process stays alive (no RakNet
   crash). The server should listen on all interfaces inside the namespace
   so clients connecting to `10.200.1.2` reach it.

### Exit criteria

- Player builds without errors
- Server starts inside the namespace, `OnServerInitialized` fires
- No RakNet crash (exit code 0 on clean shutdown, not 134)

---

## Phase 3: External DLL & Experiment Runner

### The DLL project

A standalone C# project (`experiments/`) that compiles against Unity's
managed assemblies (`UnityEngine.dll` from the built player's
`Managed/` directory). Produces `Experiments.dll`.

Build with `mcs` (Mono compiler) — no Unity editor needed.
Prerequisite: `which mcs || sudo apt install -y mono-mcs`

```bash
mcs -target:library -out:Experiments.dll \
  -r:../Builds/Linux/Player_Data/Managed/UnityEngine.dll \
  IExperiment.cs ConnectExperiment.cs
```

The `IExperiment.cs` source is shared (symlinked or copied) from the
Unity project so both sides agree on the interface.

### The runner script

A bash script (`run-experiment.sh`) that orchestrates a full capture run:

```bash
./run-experiment.sh <experiment-name> [extra-args...]
```

It:

1. Copies `Experiments.dll` into the player's expected location
2. Starts `tshark` on `lo` inside the namespace writing to
   `captures/<experiment-name>-<timestamp>.pcap`
3. Starts the server inside the namespace
4. Waits for the server to be ready (parse stdout for a marker line)
5. Starts the client inside the same namespace, pointed at `127.0.0.1`
6. Waits for experiment completion (the experiment signals done via a
   marker line, or a timeout)
7. Kills server, client, tshark
8. Prints the pcap path

All stdout/stderr from server and client is tee'd to log files alongside
the pcap.

### Exit criteria

- `mcs` compiles a trivial experiment (no-op `Setup`/`Tick`/`Shutdown`)
  against the player's `UnityEngine.dll`
- `run-experiment.sh` orchestrates server + client + tshark end-to-end
- A pcap file is produced in `captures/`
- Server and client logs are saved alongside the pcap

---

## Phase 4: First Experiment — Connection Handshake

### ConnectExperiment

The simplest possible experiment: client connects to server, both sides
log the connection callbacks, wait 2 seconds, then signal done.

No RPCs, no state sync, no instantiation. The goal is to capture:

- RakNet's connection handshake (known from the open source)
- Any Unity-level messages sent during `Network.Connect` →
  `OnConnectedToServer` / `OnPlayerConnected`
- The quiet baseline to diff against when we add RPCs

### Exit criteria

- `ConnectExperiment` runs via `run-experiment.sh connect`
- pcap saved to `captures/connect-<timestamp>.pcap`
- We can open the pcap and identify the RakNet handshake datagrams
- Server and client logs show the connection callbacks firing
- The capture shows any post-handshake Unity-level messages (or confirms
  there are none beyond the RakNet layer)
- Payload bytes are readable plaintext (confirming encryption is off)

---

## Phase 5: Systematic Experiment Coverage

Once the harness is proven with the connection experiment, build out
experiments covering each facet of Unity's legacy networking. Each
experiment is a class in the DLL; each produces its own named pcap.

### Experiment list (not exhaustive — expand as we learn)

| Experiment | What it exercises | What we're looking for |
|---|---|---|
| `connect` | Bare connection | Unity-layer handshake messages, if any |
| `rpc-void` | `RPC("Method", RPCMode.Server)` with no params | RPC name encoding, base RPC framing |
| `rpc-int` | RPC with one `int` param, vary the value | int serialization, param framing |
| `rpc-string` | RPC with one `string` param | string encoding (length-prefixed? null-terminated?) |
| `rpc-float` | RPC with one `float` param | float serialization |
| `rpc-vector3` | RPC with `Vector3` param | composite type serialization |
| `rpc-multi-param` | RPC with `(int, float, string)` | multi-param layout, separators/headers |
| `rpc-bytes` | RPC with `byte[]` param | raw byte array framing |
| `rpc-modes` | Same RPC sent via each `RPCMode` | mode encoding differences |
| `rpc-buffered` | `RPCMode.AllBuffered` then late-join a client | buffered RPC replay mechanism |
| `rpc-name-vary` | Same signature, different method names | confirms/cracks the name→hash scheme |
| `serialize-basic` | `OnSerializeNetworkView` writing a few primitives | state-sync framing, stream layout |
| `serialize-types` | Vary types written to the stream | per-type encoding in the stream |
| `serialize-rate` | Default send rate, observe timing | send interval, any rate metadata |
| `instantiate` | `Network.Instantiate` a prefab | instantiate message format |
| `destroy` | `Network.Destroy` | destroy message |
| `groups` | `SetSendingEnabled` / `SetReceivingEnabled`, group-filtered RPCs | group ID encoding, filtering |
| `viewid` | Multiple `NetworkView`s, RPCs on each | NetworkViewID encoding across views |
| `disconnect` | Client disconnects, server observes | disconnect message, cleanup |
| `multiple-clients` | 2+ clients, RPCs between them via server | multi-player message routing |

### Analysis approach

For each experiment:

1. Run it, save the pcap + logs
2. Parse the pcap with the evolving decoder (Python script initially)
3. Document findings in `docs/research/<date>-<topic>.md`
4. Update the Lua dissector as fields are confirmed

The decoder and dissector are iterative — each experiment teaches us more,
and we re-run earlier pcaps against the improved tools to confirm
consistency.

### Exit criteria for M1

Phases 1–4 are the hard gate: the harness works, we can build/run/capture.
Phase 5 is the ongoing body of work — M1 is done when the first
`connect` experiment produces a clean capture and we've confirmed we can
read the RakNet handshake in it.

---

## Decisions (resolved from review)

- **RPC forwarding**: Option B (pre-declared typed RPCs). Add methods as
  needed; rebuild the Unity project only when adding new signatures.
- **OnSerializeNetworkView**: Start with one NetworkView; experiments can
  request additional views via `ExperimentContext.CreateNetworkView()`.
- **Experiment timing**: `Tick()` with frame counting. No coroutine API —
  keep the interface simple; experiments that need sequencing use a state
  variable and frame counter.
- **DLL loading**: `Assembly.LoadFrom()` from an explicit path
  (`Experiments/Experiments.dll` next to the player binary). Avoids type
  resolution conflicts from having `IExperiment` potentially in two
  assemblies if dropped into `Managed/`.
- **Capture interface**: Both processes run inside the same namespace on
  `127.0.0.1`. Traffic to a local IP (even a veth IP) is delivered via
  the kernel loopback path and never hits the wire, so host-side capture
  on the veth would see nothing. Instead, capture on `lo` **inside** the
  namespace: `sudo ip netns exec unitynet tshark -i lo ...`. The
  namespace is isolated so lo has no noise from other system traffic.
- **Encryption**: `Network.InitializeSecurity()` is never called. Phase 4
  exit criteria include confirming payloads are plaintext.
- **Phase 5 scope**: The experiment table is the backlog for M2+, included
  here for context. M1 is done when Phase 4 exits cleanly.
