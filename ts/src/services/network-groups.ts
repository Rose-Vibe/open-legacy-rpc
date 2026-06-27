import type { ClientSession } from '../raknet/connection.js';

export class NetworkGroups {
  private viewGroups = new Map<number, number>();
  private clientSubscriptions = new Map<string, Set<number>>();
  private clientSessions = new Map<string, ClientSession>();

  /** Add a client session. Auto-subscribes to group 0. */
  addClient(session: ClientSession): void {
    this.clientSessions.set(session.id, session);
    this.clientSubscriptions.set(session.id, new Set([0]));
  }

  removeClient(session: ClientSession): void {
    this.clientSubscriptions.delete(session.id);
    this.clientSessions.delete(session.id);
  }

  subscribe(session: ClientSession, group: number): void {
    let subs = this.clientSubscriptions.get(session.id);
    if (!subs) {
      subs = new Set([0]);
      this.clientSubscriptions.set(session.id, subs);
      this.clientSessions.set(session.id, session);
    }
    subs.add(group);
  }

  unsubscribe(session: ClientSession, group: number): void {
    const subs = this.clientSubscriptions.get(session.id);
    if (subs) subs.delete(group);
  }

  setViewGroup(viewId: number, group: number): void {
    this.viewGroups.set(viewId, group);
  }

  removeView(viewId: number): void {
    this.viewGroups.delete(viewId);
  }

  getViewGroup(viewId: number): number | undefined {
    return this.viewGroups.get(viewId);
  }

  canReceive(session: ClientSession, viewId: number): boolean {
    const group = this.viewGroups.get(viewId);
    if (group === undefined) return false;
    const subs = this.clientSubscriptions.get(session.id);
    if (!subs) return false;
    return subs.has(group);
  }

  getReceivers(viewId: number): ClientSession[] {
    const group = this.viewGroups.get(viewId);
    if (group === undefined) return [];
    const receivers: ClientSession[] = [];
    for (const [sessionId, subs] of this.clientSubscriptions) {
      if (subs.has(group)) {
        const session = this.clientSessions.get(sessionId);
        if (session) receivers.push(session);
      }
    }
    return receivers;
  }

  getClientGroups(session: ClientSession): Set<number> {
    return new Set(this.clientSubscriptions.get(session.id) ?? []);
  }
}
