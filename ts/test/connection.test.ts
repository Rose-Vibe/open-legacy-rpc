import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RakNetServer, RakNetClient, ConnectionState } from '../src/raknet/connection.js';
import type { ClientSession } from '../src/raknet/connection.js';
import type { IncomingMessage } from '../src/raknet/types.js';
import { Reliability, createFrame } from '../src/raknet/types.js';
import { buildDataPacket, parsePacket } from '../src/raknet/packet.js';
import type { UdpSocket } from '../src/raknet/socket.js';

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

function readU32BE(buf: Uint8Array, offset: number): number {
  return (
    ((buf[offset]! << 24) |
      (buf[offset + 1]! << 16) |
      (buf[offset + 2]! << 8) |
      buf[offset + 3]!) >>>
    0
  );
}

const CLIENT = { host: '10.0.0.1', port: 5000 };

function doFullHandshake(socket: MockSocket): void {
  const req = new Uint8Array(1464);
  req[0] = 0x09;
  socket.triggerMessage(req, CLIENT);

  const connReq = new Uint8Array(25);
  connReq[0] = 0x04;
  const f1 = createFrame(connReq, Reliability.RELIABLE);
  f1.reliableMsgNumber = 0;
  socket.triggerMessage(buildDataPacket(0, [f1]), CLIENT);

  const newInc = new Uint8Array(67);
  newInc[0] = 0x11;
  const f2 = createFrame(newInc, Reliability.RELIABLE);
  f2.reliableMsgNumber = 1;
  f2.orderingIndex = 0;
  f2.orderingChannel = 0;
  socket.triggerMessage(buildDataPacket(1, [f2]), CLIENT);

  const ready = new Uint8Array(5);
  ready[0] = 0x83;
  ready[4] = 1;
  const f3 = createFrame(ready, Reliability.RELIABLE);
  f3.reliableMsgNumber = 2;
  f3.orderingIndex = 1;
  f3.orderingChannel = 0;
  socket.triggerMessage(buildDataPacket(2, [f3]), CLIENT);
}

describe('RakNetServer', () => {
  let serverSocket: MockSocket;
  let server: RakNetServer;

  beforeEach(() => {
    vi.useFakeTimers();
    serverSocket = createMockSocket(7777);
    server = new RakNetServer(serverSocket, { port: 7777 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('responds to open connection request with reply', async () => {
    await server.start();
    const req = new Uint8Array(1464);
    req[0] = 0x09;
    req[1] = 0x0b;
    serverSocket.triggerMessage(req, CLIENT);

    expect(serverSocket.sent.length).toBeGreaterThanOrEqual(1);
    const reply = serverSocket.sent[0]!;
    expect(reply.data[0]).toBe(0x0a);
    expect(reply.host).toBe(CLIENT.host);
    expect(reply.port).toBe(CLIENT.port);
    await server.stop();
  });

  it('creates session on open connection request', async () => {
    await server.start();
    const req = new Uint8Array(1464);
    req[0] = 0x09;
    serverSocket.triggerMessage(req, CLIENT);

    expect(server.clients.size).toBe(1);
    const session = server.getSession('10.0.0.1:5000');
    expect(session).toBeDefined();
    expect(session!.state).toBe(ConnectionState.CONNECTING);
    await server.stop();
  });

  it('rejects wrong password', async () => {
    const pwServer = new RakNetServer(serverSocket, { port: 7777, password: 'secret' });
    await pwServer.start();

    const req = new Uint8Array(1464);
    req[0] = 0x09;
    serverSocket.triggerMessage(req, CLIENT);
    expect(pwServer.clients.size).toBe(1);

    const wrongPw = new TextEncoder().encode('wrong');
    const connReq = new Uint8Array(1 + 16 + 8 + wrongPw.length);
    connReq[0] = 0x04;
    connReq.set(wrongPw, 25);
    const frame = createFrame(connReq, Reliability.RELIABLE);
    frame.reliableMsgNumber = 0;
    serverSocket.triggerMessage(buildDataPacket(0, [frame]), CLIENT);

    expect(pwServer.clients.size).toBe(0);
    await pwServer.stop();
  });

  it('accepts correct password', async () => {
    const pwServer = new RakNetServer(serverSocket, { port: 7777, password: 'secret' });
    await pwServer.start();
    const connectHandler = vi.fn();
    pwServer.onConnect(connectHandler);

    const req = new Uint8Array(1464);
    req[0] = 0x09;
    serverSocket.triggerMessage(req, CLIENT);

    const pw = new TextEncoder().encode('secret');
    const connReq = new Uint8Array(1 + 16 + 8 + pw.length);
    connReq[0] = 0x04;
    connReq.set(pw, 25);
    const f1 = createFrame(connReq, Reliability.RELIABLE);
    f1.reliableMsgNumber = 0;
    serverSocket.triggerMessage(buildDataPacket(0, [f1]), CLIENT);

    const newInc = new Uint8Array(67);
    newInc[0] = 0x11;
    const f2 = createFrame(newInc, Reliability.RELIABLE);
    f2.reliableMsgNumber = 1;
    f2.orderingIndex = 0;
    f2.orderingChannel = 0;
    serverSocket.triggerMessage(buildDataPacket(1, [f2]), CLIENT);

    const ready = new Uint8Array(5);
    ready[0] = 0x83;
    const f3 = createFrame(ready, Reliability.RELIABLE);
    f3.reliableMsgNumber = 2;
    f3.orderingIndex = 1;
    f3.orderingChannel = 0;
    serverSocket.triggerMessage(buildDataPacket(2, [f3]), CLIENT);

    expect(connectHandler).toHaveBeenCalledTimes(1);
    await pwServer.stop();
  });

  it('emits connect event after player ready', async () => {
    await server.start();
    const connectHandler = vi.fn();
    server.onConnect(connectHandler);

    doFullHandshake(serverSocket);

    expect(connectHandler).toHaveBeenCalledTimes(1);
    const session: ClientSession = connectHandler.mock.calls[0]![0] as ClientSession;
    expect(session.playerIndex).toBe(1);
    expect(session.state).toBe(ConnectionState.CONNECTED);
    await server.stop();
  });

  it('allocates sequential player indices', async () => {
    await server.start();
    const sessions: ClientSession[] = [];
    server.onConnect((s) => sessions.push(s));

    for (let clientIdx = 0; clientIdx < 2; clientIdx++) {
      const port = 5000 + clientIdx;
      const remote = { host: '10.0.0.1', port };

      const req = new Uint8Array(1464);
      req[0] = 0x09;
      serverSocket.triggerMessage(req, remote);

      const connReq = new Uint8Array(25);
      connReq[0] = 0x04;
      const f1 = createFrame(connReq, Reliability.RELIABLE);
      f1.reliableMsgNumber = 0;
      serverSocket.triggerMessage(buildDataPacket(0, [f1]), remote);

      const newInc = new Uint8Array(67);
      newInc[0] = 0x11;
      const f2 = createFrame(newInc, Reliability.RELIABLE);
      f2.reliableMsgNumber = 1;
      f2.orderingIndex = 0;
      f2.orderingChannel = 0;
      serverSocket.triggerMessage(buildDataPacket(1, [f2]), remote);

      const ready = new Uint8Array(5);
      ready[0] = 0x83;
      const f3 = createFrame(ready, Reliability.RELIABLE);
      f3.reliableMsgNumber = 2;
      f3.orderingIndex = 1;
      f3.orderingChannel = 0;
      serverSocket.triggerMessage(buildDataPacket(2, [f3]), remote);
    }

    expect(sessions).toHaveLength(2);
    expect(sessions[0]!.playerIndex).toBe(1);
    expect(sessions[1]!.playerIndex).toBe(2);
    await server.stop();
  });

  it('sends ViewID block on player ready', async () => {
    await server.start();

    doFullHandshake(serverSocket);

    // Advance timer to trigger tick which flushes reliability queue
    vi.advanceTimersByTime(100);

    let found0x81 = false;
    for (const pkt of serverSocket.sent) {
      if (pkt.data.length > 12) {
        const parsed = parsePacket(pkt.data);
        if (parsed.type === 'data') {
          for (const frame of parsed.frames) {
            if (frame.payload[0] === 0x81 && frame.payload.length === 29) {
              found0x81 = true;
              expect(readU32BE(frame.payload, 9)).toBe(1);
              expect(readU32BE(frame.payload, 13)).toBe(50);
            }
          }
        }
      }
    }
    expect(found0x81).toBe(true);
    await server.stop();
  });

  it('handles disconnect notification', async () => {
    await server.start();
    const disconnectHandler = vi.fn();
    server.onDisconnect(disconnectHandler);

    doFullHandshake(serverSocket);
    expect(server.clients.size).toBe(1);

    const disc = new Uint8Array([0x15]);
    const f4 = createFrame(disc, Reliability.RELIABLE);
    f4.reliableMsgNumber = 3;
    f4.orderingIndex = 2;
    f4.orderingChannel = 0;
    serverSocket.triggerMessage(buildDataPacket(3, [f4]), CLIENT);

    expect(disconnectHandler).toHaveBeenCalledTimes(1);
    expect(server.clients.size).toBe(0);
    await server.stop();
  });

  it('forwards non-internal messages to message handler', async () => {
    await server.start();
    const msgHandler = vi.fn();
    server.onMessage(msgHandler);

    doFullHandshake(serverSocket);

    const unityMsg = new Uint8Array([0x1b, 0x42, 0x43]);
    const f4 = createFrame(unityMsg, Reliability.RELIABLE_ORDERED);
    f4.reliableMsgNumber = 3;
    f4.orderingIndex = 0;
    f4.orderingChannel = 0;
    serverSocket.triggerMessage(buildDataPacket(3, [f4]), CLIENT);

    expect(msgHandler).toHaveBeenCalledTimes(1);
    const msg: IncomingMessage = msgHandler.mock.calls[0]![1] as IncomingMessage;
    expect(msg.payload).toEqual(new Uint8Array([0x1b, 0x42, 0x43]));
    await server.stop();
  });
});

describe('RakNetClient', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends open connection request on connect', async () => {
    const clientSocket = createMockSocket(6000);
    const client = new RakNetClient(clientSocket);

    const connectPromise = client.connect('127.0.0.1', 7777, { timeout: 100 }).catch(() => {});

    // Allow the async bind() to resolve
    await vi.dynamicImportSettled();
    await new Promise((r) => {
      setTimeout(r, 0);
    });

    expect(clientSocket.sent.length).toBeGreaterThanOrEqual(1);
    const req = clientSocket.sent[0]!;
    expect(req.data[0]).toBe(0x09);
    expect(req.host).toBe('127.0.0.1');
    expect(req.port).toBe(7777);

    await client.close();
    await connectPromise;
  });

  it('transitions to CONNECTED after full handshake', async () => {
    vi.useFakeTimers();
    const clientSocket = createMockSocket(6000);
    const client = new RakNetClient(clientSocket);

    const connectPromise = client.connect('127.0.0.1', 7777, { timeout: 5000 });
    await vi.advanceTimersByTimeAsync(10);

    // Server sends open connection reply
    const reply = new Uint8Array(1464);
    reply[0] = 0x0a;
    clientSocket.triggerMessage(reply, { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    // Server sends connection accepted (via reliability)
    const accepted = new Uint8Array(75);
    accepted[0] = 0x0e;
    const f1 = createFrame(accepted, Reliability.RELIABLE_ORDERED);
    f1.reliableMsgNumber = 0;
    f1.orderingIndex = 0;
    f1.orderingChannel = 0;
    clientSocket.triggerMessage(buildDataPacket(0, [f1]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    // Server sends player assignment (ViewID block)
    // Format: 0x81 + 7 u32BE fields
    const assignment = new Uint8Array(29);
    const dv = new DataView(assignment.buffer);
    assignment[0] = 0x81;
    dv.setUint32(1, 1); // constant 1
    dv.setUint32(5, 0); // constant 0
    dv.setUint32(9, 1); // playerIndex
    dv.setUint32(13, 50); // viewIdStride
    dv.setUint32(17, 2); // constant 2
    dv.setUint32(21, 1); // blockStart (player*2-1)
    dv.setUint32(25, 2); // blockEnd (player*2)
    const f2 = createFrame(assignment, Reliability.RELIABLE_ORDERED);
    f2.reliableMsgNumber = 1;
    f2.orderingIndex = 1;
    f2.orderingChannel = 0;
    clientSocket.triggerMessage(buildDataPacket(1, [f2]), { host: '127.0.0.1', port: 7777 });
    await vi.advanceTimersByTimeAsync(100);

    await connectPromise;
    expect(client.connected).toBe(true);
    expect(client.playerIndex).toBe(1);
    expect(client.viewIdBase).toBe(50); // blockStart(1) * stride(50)
    await client.close();
  });
});
