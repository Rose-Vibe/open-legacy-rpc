# RakNet IP Address Limit Crash

**Discovered**: 2026-06-26 (in the distance-server project; applies identically here)

## The Bug

Unity 2018's legacy networking (RakNet) crashes with SIGABRT in its native
`UpdateNetworkLoop` thread when the host system has more than ~10 IPv4
addresses. The crash is a null pointer dereference caused by a fixed-size
array overflow in RakNet's interface enumeration code.

### Symptoms

- `Network.InitializeServer()` appears to succeed (the managed call returns)
- The native `UpdateNetworkLoop` thread immediately crashes:
  ```
  Receiving unhandled NULL exception
  #0  __sigaction
  #1  UpdateNetworkLoop(void*)
  ```
- Exit code 134 (SIGABRT)
- Affects ALL Unity 2018.1 Linux builds regardless of build options

### Root Cause

RakNet internally calls `getifaddrs()` to enumerate network interfaces and
stores them in a fixed-size array (`MAXIMUM_NUMBER_OF_INTERNAL_IDS`, typically
10). Systems with many Docker bridges, Tailscale, VPNs, etc. easily exceed
this limit.

### Verification

Running in a network namespace with only loopback (1 IP) eliminates the crash:

```bash
sudo unshare --net bash -c 'ip link set lo up && ./Player.x86_64 -batchmode -nographics'
```

## The Fix

Run Unity processes in a dedicated network namespace. This repo includes
setup/teardown scripts — see `netns-setup.sh` and `netns-teardown.sh` in the
repo root.

## Alternatives Considered

- **Prune Docker networks**: fragile — creating containers brings them back
- **LD_PRELOAD shim**: intercept `getifaddrs()` to filter interfaces; no sudo but hacky
- **Docker container**: isolated namespace automatically but adds container overhead
- **User namespaces (`unshare --user --net`)**: no sudo but can't create veth bridges
