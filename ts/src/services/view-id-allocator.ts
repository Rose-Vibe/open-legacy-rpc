import type { ClientSession } from '../raknet/connection.js';

export class ViewIdAllocator {
  private readonly stride: number;
  private nextSceneId = 0;
  private clientCounters = new Map<string, number>();
  private viewIdOwners = new Map<number, ClientSession | 'server'>();
  private clientViewIds = new Map<string, number[]>();

  constructor(options?: { stride?: number }) {
    this.stride = options?.stride ?? 50;
  }

  allocateForClient(session: ClientSession): number {
    const offset = this.clientCounters.get(session.id) ?? 0;
    const viewId = session.viewIdBase + offset;
    if (viewId >= session.viewIdEnd) {
      throw new Error(`ViewID range exhausted for client ${session.id}`);
    }
    this.clientCounters.set(session.id, offset + 1);

    this.viewIdOwners.set(viewId, session);
    const list = this.clientViewIds.get(session.id) ?? [];
    list.push(viewId);
    this.clientViewIds.set(session.id, list);

    return viewId;
  }

  allocateScene(): number {
    const viewId = this.nextSceneId++;
    this.viewIdOwners.set(viewId, 'server');
    return viewId;
  }

  releaseClient(session: ClientSession): void {
    const list = this.clientViewIds.get(session.id) ?? [];
    for (const vid of list) {
      this.viewIdOwners.delete(vid);
    }
    this.clientViewIds.delete(session.id);
    this.clientCounters.delete(session.id);
  }

  getOwner(viewId: number): ClientSession | 'server' | undefined {
    return this.viewIdOwners.get(viewId);
  }

  getViewIdsForClient(session: ClientSession): number[] {
    return [...(this.clientViewIds.get(session.id) ?? [])];
  }
}
