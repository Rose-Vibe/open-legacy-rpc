import { describe, it, expect } from 'vitest';
import { ViewIdAllocator } from '../src/services/view-id-allocator.js';
import { ObjectStateTracker } from '../src/services/object-state-tracker.js';
import {
  int32,
  float32,
  string,
  bytes,
  vector3,
  quaternion,
  viewId,
  networkPlayer,
  createMessageSerializer,
} from '../src/services/serialization.js';
import { ServerCluster } from '../src/services/server-cluster.js';
import { BitStream } from '../src/bitstream.js';
import type { ClientSession } from '../src/raknet/connection.js';
import { ConnectionState } from '../src/raknet/connection.js';
import { ReliabilityLayer } from '../src/raknet/reliability.js';
import type { UnityServer } from '../src/unity/server.js';

function makeSession(id: string, playerIndex: number, viewIdBase: number): ClientSession {
  return {
    id,
    address: { host: '127.0.0.1', port: 5000 },
    playerIndex,
    viewIdBase,
    viewIdEnd: viewIdBase + 50,
    state: ConnectionState.CONNECTED,
    reliability: new ReliabilityLayer({ host: '127.0.0.1', port: 5000 }),
  };
}

describe('ViewIdAllocator', () => {
  it('allocates scene ViewIDs sequentially', () => {
    const alloc = new ViewIdAllocator();
    expect(alloc.allocateScene()).toBe(0);
    expect(alloc.allocateScene()).toBe(1);
    expect(alloc.allocateScene()).toBe(2);
  });

  it('allocates client ViewIDs from session base', () => {
    const alloc = new ViewIdAllocator();
    const session = makeSession('c1', 1, 50);
    expect(alloc.allocateForClient(session)).toBe(50);
    expect(alloc.allocateForClient(session)).toBe(51);
  });

  it('tracks ownership', () => {
    const alloc = new ViewIdAllocator();
    const session = makeSession('c1', 1, 50);
    alloc.allocateForClient(session);
    alloc.allocateScene();

    expect(alloc.getOwner(50)).toBe(session);
    expect(alloc.getOwner(0)).toBe('server');
    expect(alloc.getOwner(999)).toBeUndefined();
  });

  it('releases client ViewIDs', () => {
    const alloc = new ViewIdAllocator();
    const session = makeSession('c1', 1, 50);
    alloc.allocateForClient(session);
    alloc.allocateForClient(session);

    expect(alloc.getViewIdsForClient(session)).toEqual([50, 51]);

    alloc.releaseClient(session);
    expect(alloc.getOwner(50)).toBeUndefined();
    expect(alloc.getOwner(51)).toBeUndefined();
    expect(alloc.getViewIdsForClient(session)).toEqual([]);
  });

  it('throws when ViewID range is exhausted', () => {
    const alloc = new ViewIdAllocator();
    const session = makeSession('c1', 1, 50);
    // viewIdEnd is 100, so 50 allocations should work
    for (let i = 0; i < 50; i++) {
      alloc.allocateForClient(session);
    }
    expect(() => alloc.allocateForClient(session)).toThrow('ViewID range exhausted');
  });
});

describe('ObjectStateTracker', () => {
  it('tracks field values and dirty flags', () => {
    const tracker = new ObjectStateTracker(1, [
      { name: 'x', type: 'float' },
      { name: 'y', type: 'float' },
    ]);

    const flags = tracker.update({ x: 1.5, y: 0 });
    expect(flags).toEqual([true, false]);

    expect(tracker.getValues()).toEqual({ x: 1.5, y: 0 });
  });

  it('produces a full-state BitStream', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'hp', type: 'int' }]);
    tracker.update({ hp: 100 });
    const bs = tracker.toBitStream();
    expect(bs.bitLength).toBe(32);
  });

  it('returns null delta when clean and not first', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'hp', type: 'int' }]);
    tracker.update({ hp: 100 });
    tracker.markClean();

    const delta = tracker.toDeltaBitStream();
    expect(delta).toBeNull();
  });

  it('returns delta data on first call via toDeltaBitStream', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'hp', type: 'int' }]);
    tracker.update({ hp: 100 });

    const delta = tracker.toDeltaBitStream();
    expect(delta).not.toBeNull();
    expect(delta?.isFirst).toBe(true);
    expect(delta?.fieldValues).toEqual([100]);
  });

  it('returns delta on first call', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'hp', type: 'int' }]);
    tracker.update({ hp: 100 });

    const result = tracker.getDirtyFieldValues();
    expect(result.isFirst).toBe(true);
    expect(result.fieldValues).toEqual([100]);
    expect(result.prevValues).toEqual([0]);
    expect(result.fieldWidths).toEqual([32]);
  });

  it('resets to first state', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'hp', type: 'int' }]);
    tracker.update({ hp: 100 });
    tracker.markClean();
    tracker.reset();

    const result = tracker.getDirtyFieldValues();
    expect(result.isFirst).toBe(true);
  });

  it('handles Vector3 fields', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'pos', type: 'Vector3' }]);
    tracker.update({ pos: [1, 2, 3] });

    const result = tracker.getDirtyFieldValues();
    expect(result.fieldValues).toEqual([1, 2, 3]);
    expect(result.fieldWidths).toEqual([32, 32, 32]);
  });

  it('handles bool fields', () => {
    const tracker = new ObjectStateTracker(1, [{ name: 'alive', type: 'bool' }]);
    const flags = tracker.update({ alive: true });
    expect(flags).toEqual([true]);

    const result = tracker.getDirtyFieldValues();
    expect(result.fieldValues).toEqual([1]);
    expect(result.fieldWidths).toEqual([1]);
  });
});

describe('Serialization', () => {
  it('round-trips int32', () => {
    const bs = new BitStream();
    int32.write(bs, 42);
    int32.write(bs, -1);
    bs.pos = 0;
    expect(int32.read(bs)).toBe(42);
    expect(int32.read(bs)).toBe(-1);
  });

  it('round-trips float32', () => {
    const bs = new BitStream();
    float32.write(bs, 3.14);
    bs.pos = 0;
    expect(float32.read(bs)).toBeCloseTo(3.14, 5);
  });

  it('round-trips string', () => {
    const bs = new BitStream();
    string.write(bs, 'hello');
    bs.pos = 0;
    expect(string.read(bs)).toBe('hello');
  });

  it('round-trips empty string', () => {
    const bs = new BitStream();
    string.write(bs, '');
    bs.pos = 0;
    expect(string.read(bs)).toBe('');
  });

  it('round-trips bytes', () => {
    const data = new Uint8Array([1, 2, 3, 4]);
    const bs = new BitStream();
    bytes.write(bs, data);
    bs.pos = 0;
    expect(bytes.read(bs)).toEqual(data);
  });

  it('round-trips vector3', () => {
    const bs = new BitStream();
    vector3.write(bs, [1.0, 2.0, 3.0]);
    bs.pos = 0;
    const result = vector3.read(bs);
    expect(result[0]).toBeCloseTo(1.0);
    expect(result[1]).toBeCloseTo(2.0);
    expect(result[2]).toBeCloseTo(3.0);
  });

  it('round-trips quaternion', () => {
    const bs = new BitStream();
    quaternion.write(bs, [0, 0, 0, 1]);
    bs.pos = 0;
    const result = quaternion.read(bs);
    expect(result).toEqual([0, 0, 0, 1]);
  });

  it('round-trips viewId', () => {
    const bs = new BitStream();
    viewId.write(bs, { scope: 'scene', id: 5 });
    bs.pos = 0;
    const result = viewId.read(bs);
    expect(result.scope).toBe('scene');
    expect(result.id).toBe(5);
  });

  it('round-trips networkPlayer', () => {
    const bs = new BitStream();
    networkPlayer.write(bs, 7);
    bs.pos = 0;
    expect(networkPlayer.read(bs)).toBe(7);
  });

  it('creates composite message serializer', () => {
    const msgSerializer = createMessageSerializer({
      playerId: int32,
      position: vector3,
      name: string,
    });

    const bs = new BitStream();
    msgSerializer.write(bs, { playerId: 1, position: [1.5, 2.5, 3.5], name: 'Alice' });
    bs.pos = 0;

    const result = msgSerializer.read(bs);
    expect(result.playerId).toBe(1);
    expect(result.position[0]).toBeCloseTo(1.5);
    expect(result.position[1]).toBeCloseTo(2.5);
    expect(result.position[2]).toBeCloseTo(3.5);
    expect(result.name).toBe('Alice');
  });
});

describe('ServerCluster', () => {
  it('manages servers', () => {
    const cluster = new ServerCluster();
    const mockServer = { clients: new Map() } as unknown as UnityServer;
    cluster.addServer('main', mockServer);
    expect(cluster.getServer('main')).toBe(mockServer);

    cluster.removeServer('main');
    expect(cluster.getServer('main')).toBeUndefined();
  });

  it('aggregates clients from all servers', () => {
    const cluster = new ServerCluster();
    const session1 = makeSession('c1', 1, 50);
    const session2 = makeSession('c2', 1, 50);

    const server1 = { clients: new Map([['c1', session1]]) } as unknown as UnityServer;
    const server2 = { clients: new Map([['c2', session2]]) } as unknown as UnityServer;

    cluster.addServer('a', server1);
    cluster.addServer('b', server2);

    const all = cluster.getAllClients();
    expect(all.size).toBe(2);
    expect(all.get('a:c1')?.session).toBe(session1);
    expect(all.get('b:c2')?.session).toBe(session2);
  });

  it('forwards RPC across servers', () => {
    const cluster = new ServerCluster();
    const session1 = makeSession('c1', 1, 50);
    const session2 = makeSession('c2', 1, 100);

    const rpcCalls: Array<{ session: ClientSession; method: string }> = [];
    const mockSendRpc = (target: ClientSession, method: string): void => {
      rpcCalls.push({ session: target, method });
    };

    const server1 = {
      clients: new Map([['c1', session1]]),
      sendRpc: mockSendRpc,
    } as unknown as UnityServer;
    const server2 = {
      clients: new Map([['c2', session2]]),
      sendRpc: mockSendRpc,
    } as unknown as UnityServer;

    cluster.addServer('a', server1);
    cluster.addServer('b', server2);

    cluster.forwardRpc({ server: server2, session: session2 }, 'RPC_Int', [
      { type: 'int', value: 42 },
    ]);

    expect(rpcCalls).toHaveLength(1);
    expect(rpcCalls[0]?.session).toBe(session2);
    expect(rpcCalls[0]?.method).toBe('RPC_Int');
  });

  it('broadcasts RPC to all servers with exclude', () => {
    const cluster = new ServerCluster();
    const session1 = makeSession('c1', 1, 50);
    const session2 = makeSession('c2', 1, 100);

    const rpcTargets: string[] = [];
    const mockSendRpc = (target: ClientSession): void => {
      rpcTargets.push(target.id);
    };

    const server1 = {
      clients: new Map([['c1', session1]]),
      sendRpc: mockSendRpc,
    } as unknown as UnityServer;
    const server2 = {
      clients: new Map([['c2', session2]]),
      sendRpc: mockSendRpc,
    } as unknown as UnityServer;

    cluster.addServer('a', server1);
    cluster.addServer('b', server2);

    cluster.broadcastAll('RPC_Void', [], { exclude: session1 });

    expect(rpcTargets).toEqual(['c2']);
  });
});
