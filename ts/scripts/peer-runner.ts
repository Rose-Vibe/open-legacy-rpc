import * as process from 'node:process';
import { UdpSocket } from '../src/raknet/socket.js';
import { UnityServer } from '../src/unity/server.js';
import { UnityClient } from '../src/unity/client.js';
import { RpcMode, RPC_MODE_FROM_NAME } from '../src/unity/rpc.js';
import type { RpcParam } from '../src/unity/rpc.js';
import type { ClientSession } from '../src/raknet/connection.js';
import type { StateSyncField } from '../src/unity/state-sync.js';

interface Step {
  action: string;
  [key: string]: unknown;
}

interface Scenario {
  testInfo: {
    testId: string;
    testName: string;
    testDescription: string;
    category: string;
    mode: string;
  };
  steps: Step[];
}

interface TestResult {
  testInfo: Scenario['testInfo'];
  validation: {
    pass: boolean;
    failures: string[];
  };
}

let portCounter = 19800;
function nextPort(): number {
  return ++portCounter;
}

const SERVER_ACTIONS = new Set(['startServer', 'assertServerConnections', 'expectServerDisconnect']);
const CLIENT_ACTIONS = new Set([
  'connect', 'disconnect', 'assertConnected', 'assertDisconnected',
  'assertPlayerIndex', 'expectConnectTimeout',
]);
const BOTH_ACTIONS = new Set(['sleep', 'poll']);

const SKIP_WAIT: Record<string, number> = {
  startServer: 3000, connect: 1000, disconnect: 300,
  sendRpc: 100, expectRpc: 100, sendStateSync: 100,
  expectStateSync: 100, assertConnected: 0, assertDisconnected: 0,
  assertPlayerIndex: 0, assertServerConnections: 200,
  expectServerDisconnect: 500,
};

function stepRole(step: Step): 'server' | 'client' | 'both' {
  const action = step.action;
  if (BOTH_ACTIONS.has(action)) return 'both';
  if (SERVER_ACTIONS.has(action)) return 'server';
  if (CLIENT_ACTIONS.has(action)) return 'client';
  if (action === 'sendRpc' || action === 'sendStateSync') {
    return step.from === 'server' ? 'server' : 'client';
  }
  if (action === 'expectRpc' || action === 'expectStateSync') {
    return step.on === 'server' ? 'server' : 'client';
  }
  return 'both';
}

class PeerTestRunner {
  private scenario: Scenario;
  private timeout: number;
  private role: 'server' | 'client' | null;
  private failures: string[] = [];
  private server: UnityServer | null = null;
  private serverSocket: UdpSocket | null = null;
  private clients: Map<string, UnityClient> = new Map();
  private clientSockets: Map<string, UdpSocket> = new Map();
  private port: number;
  private serverConnected: Array<{ session: ClientSession; index: number }> = [];
  private serverDisconnected: Array<{ session: ClientSession; index: number }> = [];
  private serverRpcs: Map<string, unknown[][]> = new Map();
  private clientRpcs: Map<string, unknown[][]> = new Map();
  private clientSyncs: Map<string, Array<{ viewId: number; data: Uint8Array; bitLength: number }>> =
    new Map();
  private clientSessions: Map<string, ClientSession> = new Map();

  constructor(scenario: Scenario & { port?: number }, timeout = 5.0, role: 'server' | 'client' | null = null) {
    this.scenario = scenario;
    this.timeout = timeout;
    this.role = role;
    this.port = scenario.port ?? nextPort();
  }

  async run(): Promise<TestResult> {
    try {
      for (const step of this.scenario.steps) {
        await this.executeStep(step);
        if (this.failures.length > 0) break;
      }
    } catch (e: unknown) {
      this.failures.push(`Step execution error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      await this.cleanup();
    }

    return {
      testInfo: this.scenario.testInfo,
      validation: {
        pass: this.failures.length === 0,
        failures: this.failures,
      },
    };
  }

  private async cleanup(): Promise<void> {
    for (const [, client] of this.clients) {
      try {
        if (client.connected) client.disconnect();
      } catch {
        // ignore
      }
    }
    if (this.server) {
      try {
        await this.server.stop();
      } catch {
        // ignore
      }
    }
    for (const [, sock] of this.clientSockets) {
      try {
        await sock.close();
      } catch {
        // ignore
      }
    }
    if (this.serverSocket) {
      try {
        await this.serverSocket.close();
      } catch {
        // ignore
      }
    }
  }

  private async executeStep(step: Step): Promise<void> {
    const action = step.action;
    if (this.role !== null) {
      const sr = stepRole(step);
      if (sr !== 'both' && sr !== this.role) {
        await this.skipStep(step);
        return;
      }
    }
    const handler = this.handlers[action];
    if (!handler) {
      this.failures.push(`Unknown action: ${action}`);
      return;
    }
    await handler.call(this, step);
  }

  private async skipStep(step: Step): Promise<void> {
    const action = step.action;

    if (this.role === 'server') {
      if (action === 'connect') {
        const clientName = (step.client as string) ?? 'default';
        const expected = this.serverConnected.length + 1;
        const deadline = Date.now() + this.timeout * 1000;
        while (this.serverConnected.length < expected && Date.now() < deadline) {
          await sleep(50);
        }
        if (this.serverConnected.length >= expected) {
          const last = this.serverConnected[this.serverConnected.length - 1];
          if (last) {
            this.clientSessions.set(clientName, last.session);
          }
        }
        return;
      }
      if (action === 'disconnect') {
        const expected = this.serverDisconnected.length + 1;
        const deadline = Date.now() + this.timeout * 1000;
        while (this.serverDisconnected.length < expected && Date.now() < deadline) {
          await sleep(50);
        }
        return;
      }
      if (action === 'expectConnectTimeout') {
        await sleep(((step.timeout as number) ?? 3.0) * 1000);
        return;
      }
    }

    if (this.role === 'client' && action === 'startServer') {
      await sleep(3000);
      return;
    }

    const wait = SKIP_WAIT[action] ?? 100;
    if (wait > 0) await sleep(wait);
  }

  private preRegisterClientHandlers(clientName: string, client: UnityClient): void {
    for (const s of this.scenario.steps) {
      if (s.action === 'expectRpc') {
        const on = (s.on as string) ?? 'server';
        const stepClient = (s.client as string) ?? on;
        const targetName = stepClient === 'client' ? 'default' : stepClient;
        if (targetName !== clientName || on === 'server') continue;
        const method = s.methodName as string;
        const key = `${clientName}:${method}`;
        if (!this.clientRpcs.has(key)) {
          this.clientRpcs.set(key, []);
          const q = this.clientRpcs.get(key)!;
          client.onRpc(method, (...args) => {
            q.push(args);
          });
        }
      }
    }

    const syncKey = `${clientName}:stateSync`;
    const hasStateSyncExpect = this.scenario.steps.some(
      (s) => s.action === 'expectStateSync',
    );
    if (hasStateSyncExpect && !this.clientSyncs.has(syncKey)) {
      this.clientSyncs.set(syncKey, []);
      const q = this.clientSyncs.get(syncKey)!;
      client.onStateSync(null, (msg) => {
        q.push({ viewId: msg.viewId, data: msg.payload, bitLength: msg.bitLength });
      });
    }
  }

  private handlers: Record<string, (step: Step) => Promise<void> | void> = {
    startServer: async (step: Step): Promise<void> => {
      const password = (step.password as string) ?? '';
      this.serverSocket = new UdpSocket();
      const opts: { port: number; password?: string } = { port: this.port };
      if (password) opts.password = password;
      this.server = new UnityServer(this.serverSocket, opts);

      this.server.onConnect((session) => {
        this.serverConnected.push({ session, index: session.playerIndex });
      });
      this.server.onDisconnect((session) => {
        this.serverDisconnected.push({ session, index: session.playerIndex });
      });

      for (const s of this.scenario.steps) {
        const method = s.methodName as string | undefined;
        if (method && !this.serverRpcs.has(method)) {
          this.serverRpcs.set(method, []);
          const m = method;
          this.server.onRpc(m, (_session, ...args) => {
            this.serverRpcs.get(m)?.push(args);
          });
        }
      }

      await this.server.start();
      await sleep(50);
    },

    connect: async (step: Step): Promise<void> => {
      const clientName = (step.client as string) ?? 'default';
      const password = (step.password as string) ?? '';
      const sock = new UdpSocket();
      this.clientSockets.set(clientName, sock);
      const client = new UnityClient(sock);
      this.clients.set(clientName, client);
      this.preRegisterClientHandlers(clientName, client);

      try {
        const connectOpts: { password?: string; timeout?: number } = {
          timeout: this.timeout * 1000,
        };
        if (password) connectOpts.password = password;
        await client.connect('127.0.0.1', this.port, connectOpts);
      } catch {
        this.failures.push(`Connect timed out for ${clientName}`);
        return;
      }
      await sleep(150);

      if (this.serverConnected.length > 0) {
        const last = this.serverConnected[this.serverConnected.length - 1];
        if (last) {
          this.clientSessions.set(clientName, last.session);
        }
      }
    },

    assertConnected: (step: Step): void => {
      const clientName = (step.client as string) ?? 'default';
      const client = this.clients.get(clientName);
      if (!client) {
        this.failures.push(`No client '${clientName}' to assert`);
        return;
      }
      if (!client.connected) {
        this.failures.push(`Client '${clientName}' is not connected`);
      }
    },

    assertDisconnected: (step: Step): void => {
      const clientName = (step.client as string) ?? 'default';
      const client = this.clients.get(clientName);
      if (!client) return;
      if (client.connected) {
        this.failures.push(`Client '${clientName}' is still connected`);
      }
    },

    assertServerConnections: (step: Step): void => {
      const expected = step.count as number;
      const actual = this.server ? this.server.clients.size : 0;
      if (actual !== expected) {
        this.failures.push(`Expected ${String(expected)} server connections, got ${String(actual)}`);
      }
    },

    assertPlayerIndex: (step: Step): void => {
      const clientName = (step.client as string) ?? 'default';
      const expected = step.index as number;
      const client = this.clients.get(clientName);
      if (!client) {
        this.failures.push(`No client '${clientName}'`);
        return;
      }
      if (client.playerIndex !== expected) {
        this.failures.push(
          `Player index: expected ${String(expected)}, got ${String(client.playerIndex)}`,
        );
      }
    },

    sendRpc: async (step: Step): Promise<void> => {
      const sender = (step.from as string) ?? 'client';
      const clientName = (step.client as string) ?? 'default';
      const method = step.methodName as string;
      const rawParams = (step.params as Array<{ type: string; value: unknown }>) ?? [];
      const params = decodeStepParams(rawParams);
      const mode = RPC_MODE_FROM_NAME[(step.mode as string) ?? 'Server'] ?? RpcMode.Server;
      const viewId = (step.viewId as number) ?? 1;

      if (sender === 'server') {
        const targetName = (step.target as string) ?? clientName;
        const session = this.clientSessions.get(targetName);
        if (session && this.server) {
          this.server.sendRpc(session, method, params, { viewId, mode });
        }
      } else {
        const client = this.clients.get(clientName);
        if (client) {
          client.sendRpc(method, params, { viewId, mode });
          await sleep(100);
        }
      }
    },

    expectRpc: async (step: Step): Promise<void> => {
      const receiver = (step.on as string) ?? 'server';
      const method = step.methodName as string;
      const expectedParams = step.params as Array<{ type: string; value: unknown }> | undefined;
      const timeout = ((step.timeout as number) ?? 2.0) * 1000;

      if (receiver === 'server') {
        const queue = this.serverRpcs.get(method) ?? [];
        if (!this.serverRpcs.has(method)) {
          this.serverRpcs.set(method, queue);
        }
        const deadline = Date.now() + timeout;
        while (queue.length === 0 && Date.now() < deadline) {
          await sleep(50);
        }
        if (queue.length === 0) {
          this.failures.push(`Did not receive RPC '${method}' within ${String(timeout / 1000)}s`);
          return;
        }
        const received = queue.shift()!;
        if (expectedParams !== undefined) {
          this.validateRpcParams(method, received, expectedParams);
        }
      } else {
        const clientName = (step.client as string) ?? receiver;
        const client = this.clients.get(clientName);
        if (!client) {
          this.failures.push(`No client '${clientName}' for expectRpc`);
          return;
        }
        const key = `${clientName}:${method}`;
        if (!this.clientRpcs.has(key)) {
          this.clientRpcs.set(key, []);
          const q = this.clientRpcs.get(key)!;
          client.onRpc(method, (...args) => {
            q.push(args);
          });
        }
        const queue = this.clientRpcs.get(key)!;
        const deadline = Date.now() + timeout;
        while (queue.length === 0 && Date.now() < deadline) {
          await sleep(50);
        }
        if (queue.length === 0) {
          this.failures.push(`Did not receive RPC '${method}' within ${String(timeout / 1000)}s`);
          return;
        }
        const received = queue.shift()!;
        if (expectedParams !== undefined) {
          this.validateRpcParams(method, received, expectedParams);
        }
      }
    },

    sendStateSync: (step: Step): void => {
      const viewId = (step.viewId as number) ?? 1;
      const rawFields = (step.fields as Array<{ type: string; value: unknown }>) ?? [];
      const fields: StateSyncField[] = rawFields.map((f) => ({
        type: f.type as StateSyncField['type'],
        value: f.value as number | number[],
      }));

      const sender = (step.from as string) ?? 'server';
      if (sender === 'server') {
        const targetName = (step.target as string) ?? 'default';
        const session = this.clientSessions.get(targetName);
        if (session && this.server) {
          const scope = (step.viewIdScope as 'scene' | 'allocated') ?? 'scene';
          this.server.sendStateSync(session, { scope, id: viewId }, fields);
        }
      }
    },

    expectStateSync: async (step: Step): Promise<void> => {
      const viewId = (step.viewId as number) ?? 1;
      const expectedFields = (step.fields as Array<{ type: string; value: unknown }>) ?? [];
      const timeout = ((step.timeout as number) ?? 2.0) * 1000;
      const receiver = (step.on as string) ?? 'client';
      const clientName = receiver === 'client' ? 'default' : receiver;

      const client = this.clients.get(clientName);
      if (!client) {
        this.failures.push(`No client '${clientName}' for expectStateSync`);
        return;
      }

      const key = `${clientName}:stateSync`;
      if (!this.clientSyncs.has(key)) {
        this.clientSyncs.set(key, []);
        const q = this.clientSyncs.get(key)!;
        client.onStateSync(null, (msg) => {
          q.push({ viewId: msg.viewId, data: msg.payload, bitLength: msg.bitLength });
        });
      }

      const queue = this.clientSyncs.get(key)!;
      const deadline = Date.now() + timeout;
      while (queue.length === 0 && Date.now() < deadline) {
        await sleep(50);
      }
      if (queue.length === 0) {
        this.failures.push(
          `Did not receive state sync for view ${String(viewId)} within ${String(timeout / 1000)}s`,
        );
        return;
      }

      // For now, just verify we received something
      queue.shift();
      // TODO: field-level validation once state sync data extraction is wired
      void expectedFields;
    },

    disconnect: async (step: Step): Promise<void> => {
      const clientName = (step.client as string) ?? 'default';
      const client = this.clients.get(clientName);
      if (client?.connected) {
        client.disconnect();
        await sleep(200);
      }
    },

    expectConnectTimeout: async (step: Step): Promise<void> => {
      const clientName = (step.client as string) ?? 'default';
      const password = (step.password as string) ?? '';
      const timeoutSec = (step.timeout as number) ?? 2.0;
      const sock = new UdpSocket();
      this.clientSockets.set(clientName, sock);
      const client = new UnityClient(sock);
      this.clients.set(clientName, client);

      try {
        const connectOpts: { password?: string; timeout?: number } = {
          timeout: timeoutSec * 1000,
        };
        if (password) connectOpts.password = password;
        await client.connect('127.0.0.1', this.port, connectOpts);
        this.failures.push(`Expected connect to time out for ${clientName}`);
      } catch {
        // Expected timeout
      }
    },

    sleep: async (step: Step): Promise<void> => {
      const duration = (step.duration as number) ?? 0.1;
      await sleep(duration * 1000);
    },

    poll: async (step: Step): Promise<void> => {
      const duration = (step.duration as number) ?? 0.2;
      await sleep(duration * 1000);
    },

    expectServerDisconnect: async (step: Step): Promise<void> => {
      const expectedCount = (step.count as number) ?? 1;
      const timeout = ((step.timeout as number) ?? 2.0) * 1000;
      const deadline = Date.now() + timeout;
      while (this.serverDisconnected.length < expectedCount && Date.now() < deadline) {
        await sleep(50);
      }
      if (this.serverDisconnected.length < expectedCount) {
        this.failures.push(
          `Expected ${String(expectedCount)} server disconnect(s), got ${String(this.serverDisconnected.length)}`,
        );
      }
    },
  };

  private validateRpcParams(
    method: string,
    actual: unknown[],
    expectedRaw: Array<{ type: string; value: unknown }>,
  ): void {
    const expected = decodeStepParams(expectedRaw).map((p) => p.value);
    if (actual.length !== expected.length) {
      this.failures.push(
        `RPC '${method}' param count: expected ${String(expected.length)}, got ${String(actual.length)}`,
      );
      return;
    }
    for (let i = 0; i < expected.length; i++) {
      const exp = expected[i];
      const act = actual[i];
      if (typeof exp === 'number' && typeof act === 'number') {
        if (Math.abs(exp - act) > 1e-5) {
          this.failures.push(
            `RPC '${method}' param[${String(i)}]: expected ${String(exp)}, got ${String(act)}`,
          );
        }
      } else if (Array.isArray(exp) && Array.isArray(act)) {
        for (let j = 0; j < exp.length; j++) {
          const e = exp[j] as number;
          const a = act[j] as number;
          if (typeof e === 'number' && Math.abs(e - a) > 1e-5) {
            this.failures.push(
              `RPC '${method}' param[${String(i)}][${String(j)}]: expected ${String(e)}, got ${String(a)}`,
            );
            break;
          }
        }
      } else if (exp instanceof Uint8Array && act instanceof Uint8Array) {
        if (exp.length !== act.length || exp.some((v, j) => v !== act[j])) {
          this.failures.push(`RPC '${method}' param[${String(i)}]: bytes mismatch`);
        }
      } else if (exp !== act) {
        this.failures.push(
          `RPC '${method}' param[${String(i)}]: expected ${JSON.stringify(exp)}, got ${JSON.stringify(act)}`,
        );
      }
    }
  }
}

function decodeStepParams(params: Array<{ type: string; value: unknown }>): RpcParam[] {
  return params.map((p) => {
    if (p.type === 'bytes') {
      const hex = p.value as string;
      const arr = new Uint8Array(hex.length / 2);
      for (let i = 0; i < hex.length; i += 2) {
        arr[i / 2] = parseInt(hex.slice(i, i + 2), 16);
      }
      return { type: 'bytes' as const, value: arr };
    }
    return { type: p.type as RpcParam['type'], value: p.value as RpcParam['value'] };
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main(): Promise<void> {
  let role: 'server' | 'client' | null = null;
  const args = process.argv.slice(2);
  const roleIdx = args.indexOf('--role');
  if (roleIdx !== -1 && args[roleIdx + 1]) {
    const val = args[roleIdx + 1];
    if (val === 'server' || val === 'client') {
      role = val;
    }
  }

  const input = await readStdin();
  let scenarios: Scenario[];
  try {
    const parsed: unknown = JSON.parse(input);
    scenarios = Array.isArray(parsed) ? (parsed as Scenario[]) : [parsed as Scenario];
  } catch (e: unknown) {
    process.stderr.write(`Invalid JSON: ${e instanceof Error ? e.message : String(e)}\n`);
    process.exit(2);
  }

  const results: TestResult[] = [];
  for (const scenario of scenarios) {
    const runner = new PeerTestRunner(scenario, 5.0, role);
    const result = await runner.run();
    results.push(result);
  }

  console.log(JSON.stringify(results, null, 2));
  process.exit(results.some((r) => !r.validation.pass) ? 1 : 0);
}

function readStdin(): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    process.stdin.on('data', (chunk: Buffer) => chunks.push(chunk));
    process.stdin.on('end', () => {
      resolve(Buffer.concat(chunks).toString());
    });
  });
}

main().catch((e: unknown) => {
  process.stderr.write(`Fatal: ${e instanceof Error ? e.message : String(e)}\n`);
  process.exit(2);
});
