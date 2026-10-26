#!/usr/bin/env python3
"""
Integration test: Python server <-> Unity client.
Start this script first, then launch Unity in client mode.

Usage:
  python3 tests/test_unity_interop_server.py [port]

Launch Unity client with:
  ./unity -- --client --experiment ClientInteropExperiment --address 10.0.0.1 --port 7777
"""
import sys
import time

from protocol.bitstream import BitStream
from protocol.unity_protocol import RPCMode
from protocol.unity_server import UnityServer


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7777

    server = UnityServer(port=port)
    received_rpcs = []
    client_addr = [None]

    def on_connect(addr, player_idx):
        print(f"Client connected: {addr} (player {player_idx})")
        client_addr[0] = addr

        print("Sending RPC_Int(777) to client...")
        server.send_rpc('RPC_Int', [777], target=addr, mode=RPCMode.All, target_view=0x2000)

    def on_disconnect(addr, player_idx):
        print(f"Client disconnected: {addr} (player {player_idx})")
        client_addr[0] = None

    def on_rpc_int(addr, val):
        print(f"  Received RPC_Int({val}) from {addr}")
        received_rpcs.append(('RPC_Int', val))

    server.on_connect(on_connect)
    server.on_disconnect(on_disconnect)
    def on_rpc_float(addr, val):
        print(f"  Received RPC_Float({val}) from {addr}")
        received_rpcs.append(('RPC_Float', val))

    server.on_rpc('RPC_Int', on_rpc_int)
    server.on_rpc('RPC_Float', on_rpc_float)

    server.start()
    print(f"Python server listening on port {port}")
    print("Waiting for Unity client to connect...")

    sync_tick = 0

    import traceback
    orig_handle_rpc = server._handle_rpc

    def debug_handle_rpc(addr, payload, bit_length):
        try:
            from protocol.unity_protocol import decode_rpc
            result = decode_rpc(payload, bit_length)
            print(f"  [decoded] {result}")
        except Exception as e:
            print(f"  [decode error] {e}")
            traceback.print_exc()
        orig_handle_rpc(addr, payload, bit_length)

    server._handle_rpc = debug_handle_rpc

    raw_msgs = []
    orig_poll = server._raknet.poll

    def debug_poll(timeout=0.0):
        msgs = orig_poll(timeout)
        for addr, msg_id, payload, reliability, bit_length in msgs:
            print(f"  [raw] msg_id=0x{msg_id:02x} reliability={reliability} "
                  f"len={len(payload)} bits={bit_length} hex={payload.hex()}")
            raw_msgs.append((addr, msg_id, payload, reliability))
        return msgs

    server._raknet.poll = debug_poll

    try:
        start = time.monotonic()
        while time.monotonic() - start < 30.0:
            server.poll(0.1)

            for peer in list(server._raknet.peers.values()):
                peer.check_retransmits()

            if client_addr[0]:
                sync_tick += 1

                if sync_tick == 30:
                    print("Sending state sync value=42...")
                    bs = BitStream()
                    bs.write_i32_be(42)
                    server.send_state_sync(0, bs, target=client_addr[0])
                elif sync_tick == 60:
                    print("Sending state sync value=99...")
                    bs = BitStream()
                    bs.write_i32_be(99)
                    server.send_state_sync(0, bs, target=client_addr[0])
                elif sync_tick == 90:
                    print("Sending RPC_Int(555) to client...")
                    server.send_rpc('RPC_Int', [555], target=client_addr[0],
                                    mode=RPCMode.All, target_view=0x2000)

        print(f"\nResults: received {len(received_rpcs)} RPCs from Unity client")
        for method, val in received_rpcs:
            print(f"  {method}({val})")

        if received_rpcs:
            print("SUCCESS: Bidirectional communication working!")
        else:
            print("WARNING: No RPCs received from Unity client")

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        server.stop()
        print("Server stopped.")


if __name__ == '__main__':
    main()
