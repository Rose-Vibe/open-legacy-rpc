import type { ClientSession } from '../raknet/connection.js';
import type { UnityServer } from '../unity/server.js';
import type { RpcParam } from '../unity/rpc.js';
import { RpcMode } from '../unity/rpc.js';
import type { ViewId } from '../unity/view-id.js';

export interface ClusterClient {
  server: UnityServer;
  session: ClientSession;
}

export class ServerCluster {
  private servers = new Map<string, UnityServer>();

  addServer(name: string, server: UnityServer): void {
    this.servers.set(name, server);
  }

  removeServer(name: string): void {
    this.servers.delete(name);
  }

  getServer(name: string): UnityServer | undefined {
    return this.servers.get(name);
  }

  getAllClients(): Map<string, ClusterClient> {
    const result = new Map<string, ClusterClient>();
    for (const [serverName, server] of this.servers) {
      for (const [sessionId, session] of server.clients) {
        result.set(`${serverName}:${sessionId}`, { server, session });
      }
    }
    return result;
  }

  forwardRpc(
    to: ClusterClient,
    methodName: string,
    params: RpcParam[],
    options: { viewId?: number; mode?: RpcMode; targetView: ViewId | number },
  ): void {
    to.server.sendRpc(to.session, methodName, params, options);
  }

  broadcastAll(
    methodName: string,
    params: RpcParam[],
    options: { exclude?: ClientSession; viewId?: number; mode?: RpcMode; targetView: ViewId | number },
  ): void {
    const viewId = options.viewId ?? 1;
    const mode = options.mode ?? RpcMode.All;
    for (const server of this.servers.values()) {
      for (const session of server.clients.values()) {
        if (options.exclude && session.id === options.exclude.id) continue;
        server.sendRpc(session, methodName, params, { viewId, mode, targetView: options.targetView });
      }
    }
  }
}
