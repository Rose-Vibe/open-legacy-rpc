import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { UnityServer } from '../src/unity/server.js';
import { UnityClient } from '../src/unity/client.js';
import type { ClientSession } from '../src/raknet/connection.js';
import { Reliability, createFrame } from '../src/raknet/types.js';
import { buildDataPacket, parsePacket } from '../src/raknet/packet.js';
import type { UdpSocket } from '../src/raknet/socket.js';
import { RpcMode } from '../src/unity/rpc.js';

type MessageCallback = (data: Uint8Array, remote: { host: string; port: number }) => void;

interface MockSocket extends UdpSocket {
  triggerMessage: MessageCallback;
  sent: Array<{ data: Uint8Array; host: string; port: number }>;
}

function createMockSocket(port = 0): MockSocket {
  let handler: MessageCallback | null = null;
  const sent: Array<{ data: Uint8Array; host: string; port: number }> = [];
  return {
    sent,
    triggerMessage(data: Uint8Array, remote: { host: string; port: number }) {
      handler?.(data, remote);
    },
    onMessage(cb: MessageCallback) {
      handler = cb;
    },
    async bind(_port: number) {
      // no-op
    },
    sendTo(data: Uint8Array, host: string, targetPort: number) {
      sent.push({ data: new Uint8Array(data), host, port: targetPort });
    },
    async close() {
      // no-op
    },
    get localPort() {
      return port;
    },
  } as unknown as MockSocket;
}

const CLIENT_ADDR = { host: '10.0.0.1', port: 5000 };

function doServerHandshake(socket: MockSocket): void {
  const req = new Uint8Array(1464);
  req[0] = 0x09;
  socket.triggerMessage(req, CLIENT_ADDR);

  const connReq = new Uint8Array(25);
  connReq[0] = 0x04;
  const f1 = createFrame(connReq, Reliability.RELIABLE);
  f1.reliableMsgNumber = 0;
  socket.triggerMessage(buildDataPacket(0, [f1]), CLIENT_ADDR);

  const newInc = new Uint8Array(67);
  newInc[0] = 0x11;
  const f2 = createFrame(newInc, Reliability.RELIABLE);
  f2.reliableMsgNumber = 1;
  f2.orderingIndex = 0;
  f2.orderingChannel = 0;
  socket.triggerMessage(buildDataPacket(1, [f2]), CLIENT_ADDR);

  const ready = new Uint8Array(5);
  ready[0] = 0x83;
  ready[4] = 1;
  const f3 = createFrame(ready, Reliability.RELIABLE);
  f3.reliableMsgNumber = 2;
  f3.orderingIndex = 1;
  f3.orderingChannel = 0;
  socket.triggerMessage(buildDataPacket(2, [f3]), CLIENT_ADDR);
}

describe('UnityServer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('emits connect event when client completes handshake', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    const connected: ClientSession[] = [];
    server.onConnect((session) => connected.push(session));

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    expect(connected).toHaveLength(1);
    expect(connected[0]?.playerIndex).toBe(1);

    await server.stop();
  });

  it('emits disconnect event', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    const disconnected: ClientSession[] = [];
    server.onDisconnect((session) => disconnected.push(session));
    server.onConnect(() => {});

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    const disc = new Uint8Array(1);
    disc[0] = 0x15;
    const f = createFrame(disc, Reliability.RELIABLE);
    f.reliableMsgNumber = 3;
    f.orderingIndex = 2;
    f.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(3, [f]), CLIENT_ADDR);

    expect(disconnected).toHaveLength(1);

    await server.stop();
  });

  it('sends RPC to a client', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    let connectedSession: ClientSession | null = null;
    server.onConnect((s) => {
      connectedSession = s;
    });

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    expect(connectedSession).not.toBeNull();

    socket.sent.length = 0;
    server.sendRpc(connectedSession!, 'RPC_Int', [{ type: 'int', value: 42 }], {
      mode: RpcMode.All,
      targetView: 0x2000,
    });
    vi.advanceTimersByTime(100);

    const dataPkts = socket.sent.filter((p) => {
      const parsed = parsePacket(p.data);
      return parsed.type === 'data';
    });
    expect(dataPkts.length).toBeGreaterThan(0);

    const lastData = parsePacket(dataPkts[dataPkts.length - 1]!.data);
    if (lastData.type === 'data') {
      const payload = lastData.frames[0]?.payload;
      expect(payload?.[0]).toBe(0x1b);
    }

    await server.stop();
  });

  it('receives RPC from a client', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    server.onConnect(() => {});

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    const received: Array<{ session: ClientSession; params: unknown[] }> = [];
    server.onRpc('RPC_Int', (session, ...params) => {
      received.push({ session, params });
    });

    // Build an RPC payload using the codec
    const { encodeRpcSubsequent } = await import('../src/unity/rpc.js');
    const rpc = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 99 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2640, // allocated view 50, within player 1's block (50-100)
    });

    const f = createFrame(rpc.data, Reliability.RELIABLE_ORDERED);
    f.reliableMsgNumber = 3;
    f.orderingIndex = 0;
    f.orderingChannel = 0;
    f.bitLength = rpc.bitLength;
    socket.triggerMessage(buildDataPacket(3, [f]), CLIENT_ADDR);

    expect(received).toHaveLength(1);
    expect(received[0]?.params).toEqual([99, 0x2640]);

    await server.stop();
  });

  it('exposes clients map', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    server.onConnect(() => {});
    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    expect(server.clients.size).toBe(1);

    await server.stop();
  });

  it('sends state sync to a client', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    let connectedSession: ClientSession | null = null;
    server.onConnect((s) => {
      connectedSession = s;
    });

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    socket.sent.length = 0;
    server.sendStateSync(connectedSession!, { scope: 'scene', id: 1 }, [
      { type: 'float', value: 1.5 },
    ]);
    vi.advanceTimersByTime(100);

    const dataPkts = socket.sent.filter((p) => {
      const parsed = parsePacket(p.data);
      return parsed.type === 'data';
    });
    expect(dataPkts.length).toBeGreaterThan(0);

    const lastData = parsePacket(dataPkts[dataPkts.length - 1]!.data);
    if (lastData.type === 'data') {
      const payload = lastData.frames[0]?.payload;
      expect(payload?.[0]).toBe(0x1b);
    }

    await server.stop();
  });

  it('handles multiple simultaneous clients', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    const connected: ClientSession[] = [];
    server.onConnect((s) => connected.push(s));

    // Connect first client
    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    // Connect second client
    const CLIENT2 = { host: '10.0.0.2', port: 5001 };
    const req2 = new Uint8Array(1464);
    req2[0] = 0x09;
    socket.triggerMessage(req2, CLIENT2);

    const connReq2 = new Uint8Array(25);
    connReq2[0] = 0x04;
    const g1 = createFrame(connReq2, Reliability.RELIABLE);
    g1.reliableMsgNumber = 0;
    socket.triggerMessage(buildDataPacket(0, [g1]), CLIENT2);

    const newInc2 = new Uint8Array(67);
    newInc2[0] = 0x11;
    const g2 = createFrame(newInc2, Reliability.RELIABLE);
    g2.reliableMsgNumber = 1;
    g2.orderingIndex = 0;
    g2.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(1, [g2]), CLIENT2);

    const ready2 = new Uint8Array(5);
    ready2[0] = 0x83;
    ready2[4] = 1;
    const g3 = createFrame(ready2, Reliability.RELIABLE);
    g3.reliableMsgNumber = 2;
    g3.orderingIndex = 1;
    g3.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(2, [g3]), CLIENT2);

    vi.advanceTimersByTime(100);

    expect(connected).toHaveLength(2);
    expect(server.clients.size).toBe(2);
    expect(connected[0]?.playerIndex).toBe(1);
    expect(connected[1]?.playerIndex).toBe(2);

    await server.stop();
  });

  it('broadcasts RPC to all clients with exclude', async () => {
    const socket = createMockSocket(7777);
    const server = new UnityServer(socket, { port: 7777 });
    await server.start();

    let session1: ClientSession | null = null;
    server.onConnect((s) => {
      session1 = s;
    });

    doServerHandshake(socket);
    vi.advanceTimersByTime(100);

    socket.sent.length = 0;
    server.broadcastRpc('RPC_Void', [], { exclude: session1! });
    vi.advanceTimersByTime(100);

    // With only 1 client and that client excluded, no data packets should be sent
    const dataPkts = socket.sent.filter((p) => {
      const parsed = parsePacket(p.data);
      return parsed.type === 'data';
    });
    expect(dataPkts).toHaveLength(0);

    await server.stop();
  });
});

describe('UnityClient', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends RPC via the client', async () => {
    const socket = createMockSocket(12345);
    const client = new UnityClient(socket);

    // Manually kick off connect (we'll simulate the server responses)
    const connectPromise = client.connect('127.0.0.1', 7777, { timeout: 5000 });

    await vi.advanceTimersByTimeAsync(10);

    // Simulate server sending open connection reply
    const reply = new Uint8Array(1464);
    reply[0] = 0x0a;
    socket.triggerMessage(reply, { host: '127.0.0.1', port: 7777 });

    await vi.advanceTimersByTimeAsync(100);

    // Find the CONNECTION_REQUEST in sent packets and simulate acceptance
    const connReqPkts = socket.sent.filter((p) => {
      const parsed = parsePacket(p.data);
      if (parsed.type === 'data') {
        return parsed.frames.some((f) => f.payload[0] === 0x04);
      }
      return false;
    });
    expect(connReqPkts.length).toBeGreaterThan(0);

    // Send CONNECTION_REQUEST_ACCEPTED
    const accepted = new Uint8Array(75);
    accepted[0] = 0x0e;
    const fa = createFrame(accepted, Reliability.RELIABLE_ORDERED);
    fa.reliableMsgNumber = 0;
    fa.orderingIndex = 0;
    fa.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(0, [fa]), { host: '127.0.0.1', port: 7777 });

    await vi.advanceTimersByTimeAsync(100);

    // Send PLAYER_ASSIGNMENT
    const assignment = new Uint8Array(29);
    assignment[0] = 0x81;
    // playerIndex = 1 at offset 9
    assignment[12] = 1;
    // viewIdStride = 50 at offset 13
    assignment[16] = 50;
    const fb = createFrame(assignment, Reliability.RELIABLE_ORDERED);
    fb.reliableMsgNumber = 1;
    fb.orderingIndex = 1;
    fb.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(1, [fb]), { host: '127.0.0.1', port: 7777 });

    await vi.advanceTimersByTimeAsync(100);
    await connectPromise;

    expect(client.connected).toBe(true);

    // Now send an RPC
    socket.sent.length = 0;
    client.sendRpc('RPC_Int', [{ type: 'int', value: 42 }], { targetView: 0x2000 });
    vi.advanceTimersByTime(100);

    const dataPkts = socket.sent.filter((p) => {
      const parsed = parsePacket(p.data);
      return parsed.type === 'data';
    });
    expect(dataPkts.length).toBeGreaterThan(0);

    client.disconnect();
  });

  it('receives RPC from server', async () => {
    const socket = createMockSocket(12345);
    const client = new UnityClient(socket);

    const connectPromise = client.connect('127.0.0.1', 7777, { timeout: 5000 });
    await vi.advanceTimersByTimeAsync(10);

    const reply = new Uint8Array(1464);
    reply[0] = 0x0a;
    socket.triggerMessage(reply, { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    const accepted = new Uint8Array(75);
    accepted[0] = 0x0e;
    const fa = createFrame(accepted, Reliability.RELIABLE_ORDERED);
    fa.reliableMsgNumber = 0;
    fa.orderingIndex = 0;
    fa.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(0, [fa]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    const assignment = new Uint8Array(29);
    assignment[0] = 0x81;
    assignment[12] = 1;
    assignment[16] = 50;
    const fb = createFrame(assignment, Reliability.RELIABLE_ORDERED);
    fb.reliableMsgNumber = 1;
    fb.orderingIndex = 1;
    fb.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(1, [fb]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);
    await connectPromise;

    const received: unknown[][] = [];
    client.onRpc('RPC_Int', (...params) => {
      received.push(params);
    });

    // Server sends RPC to client
    const { encodeRpcSubsequent } = await import('../src/unity/rpc.js');
    const rpc = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 77 }],
      timestampMs: 0,
      mode: RpcMode.All,
      targetView: 0x2000,
    });

    const fc = createFrame(rpc.data, Reliability.RELIABLE_ORDERED);
    fc.reliableMsgNumber = 2;
    fc.orderingIndex = 2;
    fc.orderingChannel = 0;
    fc.bitLength = rpc.bitLength;
    socket.triggerMessage(buildDataPacket(2, [fc]), { host: '127.0.0.1', port: 7777 });

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual([77]);

    client.disconnect();
  });

  it('fires connect and disconnect events', async () => {
    const socket = createMockSocket(12345);
    const client = new UnityClient(socket);

    const connectEvents: boolean[] = [];
    const disconnectEvents: string[] = [];
    client.onConnect(() => connectEvents.push(true));
    client.onDisconnect((reason) => disconnectEvents.push(reason));

    const connectPromise = client.connect('127.0.0.1', 7777, { timeout: 5000 });
    await vi.advanceTimersByTimeAsync(10);

    const reply = new Uint8Array(1464);
    reply[0] = 0x0a;
    socket.triggerMessage(reply, { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    const accepted = new Uint8Array(75);
    accepted[0] = 0x0e;
    const fa = createFrame(accepted, Reliability.RELIABLE_ORDERED);
    fa.reliableMsgNumber = 0;
    fa.orderingIndex = 0;
    fa.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(0, [fa]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    const assignment = new Uint8Array(29);
    assignment[0] = 0x81;
    assignment[12] = 1;
    assignment[16] = 50;
    const fb = createFrame(assignment, Reliability.RELIABLE_ORDERED);
    fb.reliableMsgNumber = 1;
    fb.orderingIndex = 1;
    fb.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(1, [fb]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);
    await connectPromise;

    expect(connectEvents).toHaveLength(1);

    // Server sends disconnect
    const disc = new Uint8Array(1);
    disc[0] = 0x15;
    const fd = createFrame(disc, Reliability.RELIABLE_ORDERED);
    fd.reliableMsgNumber = 2;
    fd.orderingIndex = 2;
    fd.orderingChannel = 0;
    socket.triggerMessage(buildDataPacket(2, [fd]), { host: '127.0.0.1', port: 7777 });

    expect(disconnectEvents).toHaveLength(1);
    expect(client.connected).toBe(false);
  });
});
