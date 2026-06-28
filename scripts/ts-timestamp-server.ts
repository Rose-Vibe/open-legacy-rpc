import { UdpSocket } from '../ts/src/raknet/socket.js';
import { UnityServer } from '../ts/src/unity/server.js';
import { encodeRpcFirstUse, RpcMode } from '../ts/src/unity/rpc.js';
import { Reliability } from '../ts/src/raknet/types.js';
import type { ClientSession } from '../ts/src/raknet/connection.js';

const PORT = 7777;
const socket = new UdpSocket();
const epochNs = process.hrtime.bigint();
const server = new UnityServer(socket, { port: PORT, epochNs });

function getUptimeMs(): number {
  return Number((process.hrtime.bigint() - epochNs) / 1_000_000n);
}

console.log(`[TS Server] Starting on port ${PORT}`);
console.log(`[TS Server] epochNs-based uptime: RPC counter and ping/pong share same clock`);

server.onConnect((session: ClientSession) => {
  console.log(`[TS Server] Client connected: ${session.id}`);

  let count = 0;
  const interval = setInterval(() => {
    count++;
    const uptimeMs = getUptimeMs();
    console.log(`[TS Server] Sending RPC #${count} value=${100 + count} uptimeMs=${uptimeMs}`);

    const result = encodeRpcFirstUse({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 100 + count }],
      timestampMs: uptimeMs,
      mode: RpcMode.Server,
      targetView: 0x0002,
    });

    // Use the RakNet server's sendTo directly via the UnityServer's internal API
    (server as any).raknet.sendTo(session, result.data, Reliability.RELIABLE_ORDERED, result.bitLength);

    if (count >= 10) {
      clearInterval(interval);
      console.log(`[TS Server] All 10 RPCs sent`);
      setTimeout(() => process.exit(0), 5000);
    }
  }, 1000);
});

server.onDisconnect(() => {
  console.log(`[TS Server] Client disconnected`);
});

server.start().then(() => {
  console.log(`[TS Server] Listening on port ${PORT}, waiting for client...`);
});
