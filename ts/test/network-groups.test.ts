import { describe, it, expect } from 'vitest';
import { NetworkGroups } from '../src/services/network-groups.js';
import type { ClientSession } from '../src/raknet/connection.js';
import { ConnectionState } from '../src/raknet/connection.js';
import { ReliabilityLayer } from '../src/raknet/reliability.js';

function makeSession(id: string): ClientSession {
  return {
    id,
    address: { host: '127.0.0.1', port: 5000 },
    playerIndex: 1,
    viewIdBase: 50,
    viewIdEnd: 100,
    state: ConnectionState.CONNECTED,
    reliability: new ReliabilityLayer({ host: '127.0.0.1', port: 5000 }),
  };
}

describe('NetworkGroups', () => {
  it('subscribes new clients to group 0 by default', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);

    expect(groups.getClientGroups(session).has(0)).toBe(true);
  });

  it('assigns views to groups', () => {
    const groups = new NetworkGroups();
    groups.setViewGroup(100, 1);
    expect(groups.getViewGroup(100)).toBe(1);
  });

  it('canReceive returns true when client is subscribed to view group', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.setViewGroup(100, 0);

    expect(groups.canReceive(session, 100)).toBe(true);
  });

  it('canReceive returns false when client is not subscribed', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.setViewGroup(200, 5);

    expect(groups.canReceive(session, 200)).toBe(false);
  });

  it('canReceive returns false for unknown views', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);

    expect(groups.canReceive(session, 999)).toBe(false);
  });

  it('subscribe adds a group', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.subscribe(session, 3);
    groups.setViewGroup(100, 3);

    expect(groups.canReceive(session, 100)).toBe(true);
    expect(groups.getClientGroups(session).has(3)).toBe(true);
  });

  it('unsubscribe removes a group', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.subscribe(session, 2);
    groups.setViewGroup(100, 2);

    expect(groups.canReceive(session, 100)).toBe(true);

    groups.unsubscribe(session, 2);
    expect(groups.canReceive(session, 100)).toBe(false);
  });

  it('getReceivers returns all subscribed clients', () => {
    const groups = new NetworkGroups();
    const s1 = makeSession('c1');
    const s2 = makeSession('c2');
    const s3 = makeSession('c3');

    groups.addClient(s1);
    groups.addClient(s2);
    groups.addClient(s3);

    groups.subscribe(s1, 1);
    groups.subscribe(s2, 1);
    groups.setViewGroup(100, 1);

    const receivers = groups.getReceivers(100);
    const ids = receivers.map((s) => s.id).sort();
    expect(ids).toEqual(['c1', 'c2']);
  });

  it('getReceivers returns empty for unknown views', () => {
    const groups = new NetworkGroups();
    expect(groups.getReceivers(999)).toEqual([]);
  });

  it('removeClient cleans up all subscriptions', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.subscribe(session, 1);
    groups.subscribe(session, 2);
    groups.setViewGroup(100, 1);

    expect(groups.canReceive(session, 100)).toBe(true);

    groups.removeClient(session);
    expect(groups.canReceive(session, 100)).toBe(false);
    expect(groups.getReceivers(100)).toEqual([]);
    expect(groups.getClientGroups(session).size).toBe(0);
  });

  it('removeView cleans up group assignment', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);
    groups.setViewGroup(100, 0);

    expect(groups.canReceive(session, 100)).toBe(true);

    groups.removeView(100);
    expect(groups.canReceive(session, 100)).toBe(false);
    expect(groups.getViewGroup(100)).toBeUndefined();
  });

  it('subscribe on unknown client auto-registers them', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.subscribe(session, 5);
    groups.setViewGroup(100, 5);

    expect(groups.canReceive(session, 100)).toBe(true);
    expect(groups.getClientGroups(session).has(0)).toBe(true);
  });

  it('handles multiple views in the same group', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);

    groups.setViewGroup(100, 0);
    groups.setViewGroup(101, 0);
    groups.setViewGroup(102, 1);

    expect(groups.canReceive(session, 100)).toBe(true);
    expect(groups.canReceive(session, 101)).toBe(true);
    expect(groups.canReceive(session, 102)).toBe(false);
  });

  it('reassigning a view to a different group works', () => {
    const groups = new NetworkGroups();
    const session = makeSession('c1');
    groups.addClient(session);

    groups.setViewGroup(100, 0);
    expect(groups.canReceive(session, 100)).toBe(true);

    groups.setViewGroup(100, 5);
    expect(groups.canReceive(session, 100)).toBe(false);

    groups.subscribe(session, 5);
    expect(groups.canReceive(session, 100)).toBe(true);
  });
});
