#!/usr/bin/env python3
"""
Integration test: Python client <-> Unity server.
Run Unity server first, then this script connects and exchanges RPCs.

Usage:
  python3 tests/test_unity_interop.py [host] [port]

Requires the Unity server to be running with an experiment that has
RPC handlers (e.g., ConnectExperiment or any experiment using Loader's RPCs).
"""
import sys

from protocol.unity_client import UnityClient


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7777

    print(f"Connecting to Unity server at {host}:{port}...")
    client = UnityClient()

    received_rpcs = []
    received_syncs = []

    client.on_rpc('RPC_Int', lambda val: received_rpcs.append(('RPC_Int', val)))
    client.on_rpc('RPC_Float', lambda val: received_rpcs.append(('RPC_Float', val)))
    client.on_rpc('RPC_String', lambda val: received_rpcs.append(('RPC_String', val)))

    def handle_sync(data_stream):
        try:
            val = data_stream.read_i32_be()
            received_syncs.append(val)
        except Exception:
            pass

    # Unity's first scene-baked NetworkView uses AllocatedID 0
    client.on_state_sync(0, handle_sync)

    try:
        client.connect(host, port, timeout=5.0)
        print(f"Connected! Player index: {client.player_index}")

        # Send some RPCs to the Unity server (view_id=0 = first scene-baked NetworkView)
        print("Sending RPC_Int(42)...")
        client.send_rpc('RPC_Int', [42], view_id=0, target_view=0x2000)

        print("Sending RPC_Int(99)...")
        client.send_rpc('RPC_Int', [99], view_id=0, target_view=0x2000)

        print("Sending RPC_Float(3.14)...")
        client.send_rpc('RPC_Float', [3.14], view_id=0, target_view=0x2000)

        print("Sending RPC_String('hello from python')...")
        client.send_rpc('RPC_String', ['hello from python'], view_id=0, target_view=0x2000)

        # Poll for a few seconds to receive any responses
        print("Polling for responses...")
        for i in range(50):
            client.poll(0.1)
            if received_rpcs:
                for method, val in received_rpcs:
                    print(f"  Received RPC: {method}({val})")
                received_rpcs.clear()
            if received_syncs:
                for val in received_syncs:
                    print(f"  Received state sync: {val}")
                received_syncs.clear()

        print("Disconnecting...")
        client.disconnect()
        print("Done!")

    except TimeoutError:
        print("ERROR: Connection timed out. Is the Unity server running?")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted")
        client.disconnect()


if __name__ == '__main__':
    main()
