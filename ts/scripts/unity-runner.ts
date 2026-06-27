import * as process from 'node:process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { spawn, execSync, type ChildProcess } from 'node:child_process';
import { UdpSocket } from '../src/raknet/socket.js';
import { UnityServer } from '../src/unity/server.js';
import { UnityClient } from '../src/unity/client.js';
import { RPC_MODE_FROM_NAME } from '../src/unity/rpc.js';
import type { RpcParam } from '../src/unity/rpc.js';
import type { ClientSession } from '../src/raknet/connection.js';

interface Step {
  action: string;
  [key: string]: unknown;
}

interface TestInfo {
  testId: string;
  testName: string;
  testDescription: string;
  category: string;
  mode: string;
}

interface Scenario {
  testInfo: TestInfo;
  steps: Step[];
}

interface TestResult {
  testInfo: TestInfo;
  validation: {
    pass: boolean;
    failures: string[];
    skipped?: boolean;
  };
}

const PROJECT_ROOT = new URL('../../', import.meta.url).pathname.replace(/\/$/, '');
const DEFAULT_UNITY_PATH = path.join(
  PROJECT_ROOT, 'UnityProject', 'Builds', 'Linux', 'Player.x86_64',
);

let portCounter = 21800;
function nextPort(): number {
  return ++portCounter;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

class UnityProcess {
  private proc: ChildProcess | null = null;
  private logPath: string;
  private logDir: string;
  private logLines: string[] = [];
  private tailInterval: ReturnType<typeof setInterval> | null = null;
  private exitCode: number | null = null;

  constructor(
    private unityPath: string,
    private experiment: string,
    private role: 'server' | 'client',
    private port: number,
    private address?: string,
    private extraArgs: string[] = [],
    logDir?: string,
  ) {
    this.logDir = logDir ?? fs.mkdtempSync(path.join(os.tmpdir(), 'unity_test_'));
    this.logPath = path.join(this.logDir, 'output_log.txt');
  }

  start(): void {
    const cmd = [
      '-batchmode', '-nographics',
      '-logFile', this.logPath,
      '--', `--${this.role}`,
      '--experiment', this.experiment,
      '--port', String(this.port),
    ];
    if (this.address) {
      cmd.push('--address', this.address);
    }
    cmd.push(...this.extraArgs);

    this.proc = spawn(this.unityPath, cmd, {
      stdio: ['ignore', 'ignore', 'ignore'],
    });
    this.proc.on('exit', (code) => {
      this.exitCode = code;
    });

    this.tailInterval = setInterval(() => { this.readLog(); }, 200);
  }

  private readLog(): void {
    try {
      if (fs.existsSync(this.logPath)) {
        const content = fs.readFileSync(this.logPath, 'utf-8');
        this.logLines = content.split('\n').map((l) => l.trimEnd());
      }
    } catch {
      // ignore read errors
    }
  }

  async waitForLog(pattern: string, timeout = 10000): Promise<string | null> {
    const regex = new RegExp(pattern);
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      this.readLog();
      for (const line of this.logLines) {
        if (regex.test(line)) return line;
      }
      if (this.exitCode !== null) {
        this.readLog();
        for (const line of this.logLines) {
          if (regex.test(line)) return line;
        }
        return null;
      }
      await sleep(200);
    }
    return null;
  }

  getExperimentLogs(): string[] {
    return this.logLines.filter((l) => l.includes('[Experiment]'));
  }

  get lines(): string[] {
    return [...this.logLines];
  }

  get running(): boolean {
    return this.proc !== null && this.exitCode === null;
  }

  stop(): void {
    if (this.tailInterval) {
      clearInterval(this.tailInterval);
      this.tailInterval = null;
    }
    if (this.proc && this.exitCode === null) {
      this.proc.kill('SIGTERM');
      setTimeout(() => {
        if (this.proc && this.exitCode === null) {
          this.proc.kill('SIGKILL');
        }
      }, 5000);
    }
  }

  cleanup(): void {
    this.stop();
    try {
      fs.rmSync(this.logDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}

function findUnityBinary(customPath?: string): string | null {
  if (customPath && fs.existsSync(customPath)) return customPath;
  if (fs.existsSync(DEFAULT_UNITY_PATH)) return DEFAULT_UNITY_PATH;
  return null;
}

class UnityTestRunner {
  private failures: string[] = [];
  private skipped = false;
  private unity: UnityProcess | null = null;
  private server: UnityServer | null = null;
  private serverSocket: UdpSocket | null = null;
  private client: UnityClient | null = null;
  private clientSocket: UdpSocket | null = null;
  private port: number;
  private unityPath: string | null;
  private serverConnected: Array<{ session: ClientSession; index: number }> = [];
  private serverRpcs: Map<string, unknown[][]> = new Map();
  private clientRpcs: Map<string, unknown[][]> = new Map();
  private masterPort: number;

  constructor(
    private scenario: Scenario,
    unityPath?: string,
    private timeout = 15000,
  ) {
    this.unityPath = findUnityBinary(unityPath);
    this.port = nextPort();
    this.masterPort = nextPort();
  }

  async run(): Promise<TestResult> {
    if (!this.unityPath) {
      return {
        testInfo: this.scenario.testInfo,
        validation: {
          pass: false,
          failures: ['Unity binary not found'],
          skipped: true,
        },
      };
    }

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

    const validation: TestResult['validation'] = {
      pass: this.failures.length === 0,
      failures: this.failures,
    };
    if (this.skipped) validation.skipped = true;
    return { testInfo: this.scenario.testInfo, validation };
  }

  private async cleanup(): Promise<void> {
    if (this.client) {
      try {
        this.client.disconnect();
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
    if (this.clientSocket) {
      try {
        await this.clientSocket.close();
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
    if (this.unity) {
      this.unity.cleanup();
    }
  }

  private preRegisterClientHandlers(client: UnityClient): void {
    for (const s of this.scenario.steps) {
      if (s.action === 'expectRpc') {
        const method = s.methodName as string;
        if (!this.clientRpcs.has(method)) {
          this.clientRpcs.set(method, []);
          const q = this.clientRpcs.get(method)!;
          client.onRpc(method, (...args) => {
            q.push(args);
          });
        }
      }
    }
  }

  private async executeStep(step: Step): Promise<void> {
    const action = step.action;
    const handler = this.handlers[action];
    if (!handler) {
      this.failures.push(`Unknown action: ${action}`);
      return;
    }
    await handler.call(this, step);
  }

  private handlers: Record<string, (step: Step) => Promise<void> | void> = {
    startUnityServer: async (step: Step): Promise<void> => {
      const experiment = step.experiment as string;
      const extraArgs: string[] = [];
      if (step.password) {
        extraArgs.push('--password', step.password as string);
      }
      if (step.passMasterPort) {
        extraArgs.push(String(this.masterPort));
      }
      extraArgs.push(...((step.extraArgs as string[]) ?? []));
      this.unity = new UnityProcess(
        this.unityPath!, experiment, 'server', this.port,
        undefined, extraArgs,
      );
      this.unity.start();
      const line = await this.unity.waitForLog(
        'Server ready|Server initialized|Listening', this.timeout,
      );
      if (line === null) {
        this.failures.push('Unity server did not become ready');
      }
    },

    startUnityClient: (step: Step): void => {
      const experiment = step.experiment as string;
      this.unity = new UnityProcess(
        this.unityPath!, experiment, 'client', this.port, '127.0.0.1',
      );
      this.unity.start();
    },

    connectToUnity: async (step: Step): Promise<void> => {
      const password = (step.password as string) ?? '';
      this.clientSocket = new UdpSocket();
      this.client = new UnityClient(this.clientSocket);
      this.preRegisterClientHandlers(this.client);
      try {
        const opts: { password?: string; timeout?: number } = {
          timeout: this.timeout,
        };
        if (password) opts.password = password;
        await this.client.connect('127.0.0.1', this.port, opts);
      } catch {
        this.failures.push('Connect to Unity timed out');
      }
    },

    assertConnected: (_step: Step): void => {
      if (!this.client?.connected) {
        this.failures.push('TS client is not connected');
      }
    },

    waitForUnityLog: async (step: Step): Promise<void> => {
      const pattern = step.pattern as string;
      const timeout = ((step.timeout as number) ?? this.timeout / 1000) * 1000;
      if (!this.unity) {
        this.failures.push('No Unity process running');
        return;
      }
      const line = await this.unity.waitForLog(pattern, timeout);
      if (line === null) {
        this.failures.push(`Unity log did not match pattern: ${pattern}`);
      }
    },

    sendRpc: async (step: Step): Promise<void> => {
      const methodName = step.methodName as string;
      const rawParams = (step.params as Array<{ type: string; value: unknown }>) ?? [];
      const params = decodeStepParams(rawParams);
      const modeName = (step.mode as string) ?? 'Server';
      const mode = RPC_MODE_FROM_NAME[modeName] ?? RPC_MODE_FROM_NAME['Server'];
      const viewId = (step.viewId as number) ?? 1;

      if (!this.client) {
        this.failures.push('No client to send RPC');
        return;
      }

      this.client.sendRpc(methodName, params, { viewId, mode });
      for (let i = 0; i < 5; i++) {
        await sleep(20);
      }
    },

    expectRpc: async (step: Step): Promise<void> => {
      const methodName = step.methodName as string;
      const timeout = ((step.timeout as number) ?? 5) * 1000;

      if (!this.client) {
        this.failures.push('No client for expectRpc');
        return;
      }

      if (!this.clientRpcs.has(methodName)) {
        this.clientRpcs.set(methodName, []);
        const q = this.clientRpcs.get(methodName)!;
        this.client.onRpc(methodName, (...args) => {
          q.push(args);
        });
      }

      const queue = this.clientRpcs.get(methodName)!;
      const deadline = Date.now() + timeout;
      while (queue.length === 0 && Date.now() < deadline) {
        await sleep(50);
      }

      if (queue.length === 0) {
        this.failures.push(`Did not receive RPC '${methodName}' from Unity`);
        return;
      }

      const received = queue.shift()!;
      const expectedParams = step.params as Array<{ type: string; value: unknown }> | undefined;
      if (expectedParams) {
        const decoded = decodeStepParams(expectedParams);
        for (let i = 0; i < decoded.length; i++) {
          const exp = decoded[i];
          const act = received[i];
          if (exp.type === 'float' || exp.type === 'double') {
            if (Math.abs((exp.value as number) - (act as number)) > 1e-5) {
              this.failures.push(`RPC param[${i}]: expected ${String(exp.value)}, got ${String(act)}`);
            }
          } else if (exp.type === 'bytes') {
            const expArr = exp.value as Uint8Array;
            const actArr = act as Uint8Array;
            if (expArr.length !== actArr?.length || !expArr.every((b, j) => b === actArr[j])) {
              this.failures.push(`RPC param[${i}]: bytes mismatch`);
            }
          } else if (exp.value !== act) {
            this.failures.push(`RPC param[${i}]: expected ${String(exp.value)}, got ${String(act)}`);
          }
        }
      }
    },

    expectServerRpc: async (step: Step): Promise<void> => {
      const methodName = step.methodName as string;
      const timeout = ((step.timeout as number) ?? 5) * 1000;
      const queue = this.serverRpcs.get(methodName);
      if (!queue) {
        this.failures.push(`No handler registered for server RPC '${methodName}'`);
        return;
      }
      const deadline = Date.now() + timeout;
      while (queue.length === 0 && Date.now() < deadline) {
        await sleep(50);
      }
      if (queue.length === 0) {
        this.failures.push(`TS server did not receive RPC '${methodName}' from Unity`);
      }
    },

    waitForUnityConnect: async (step: Step): Promise<void> => {
      const timeout = ((step.timeout as number) ?? this.timeout / 1000) * 1000;
      const deadline = Date.now() + timeout;
      while (this.serverConnected.length === 0 && Date.now() < deadline) {
        await sleep(100);
      }
      if (this.serverConnected.length === 0) {
        this.failures.push('Unity client did not connect to TS server');
      }
    },

    startPythonServer: async (step: Step): Promise<void> => {
      const password = (step.password as string) ?? '';
      this.serverSocket = new UdpSocket();
      const opts: { port: number; password?: string } = { port: this.port };
      if (password) opts.password = password;
      this.server = new UnityServer(this.serverSocket, opts);

      this.server.onConnect((session) => {
        this.serverConnected.push({ session, index: session.playerIndex });
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

    startMasterServer: (_step: Step): void => {
      this.skipped = true;
      this.failures.push('Master server not implemented in TS (M11 is Python-only)');
    },

    expectMasterRegistration: (_step: Step): void => {
      // Only reached if startMasterServer didn't fail first
    },

    disconnect: async (_step: Step): Promise<void> => {
      if (this.client?.connected) {
        this.client.disconnect();
        await sleep(300);
      }
    },

    sleep: async (step: Step): Promise<void> => {
      const duration = (step.duration as number) ?? 0.5;
      await sleep(duration * 1000);
    },
  };
}

async function loadScenarios(): Promise<Record<string, Scenario>> {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', [
      '-c',
      'import json; from conformance.generators.unity.scenarios import SCENARIOS; print(json.dumps(SCENARIOS))',
    ], { cwd: PROJECT_ROOT });
    const chunks: Buffer[] = [];
    proc.stdout.on('data', (chunk: Buffer) => chunks.push(chunk));
    proc.stderr.on('data', (chunk: Buffer) => process.stderr.write(chunk));
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Failed to load scenarios (exit ${String(code)})`));
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString()) as Record<string, Scenario>);
      } catch (e: unknown) {
        reject(new Error(`Failed to parse scenarios: ${e instanceof Error ? e.message : String(e)}`));
      }
    });
  });
}

function checkNetworkNamespace(): boolean {
  try {
    const ns = execSync('ip netns identify $$', { encoding: 'utf-8' }).trim();
    return ns === 'unitynet';
  } catch {
    return false;
  }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const filterArgs: string[] = [];
  let unityPath: string | undefined;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--unity-path' && args[i + 1]) {
      unityPath = args[++i];
    } else if (!args[i].startsWith('-')) {
      filterArgs.push(args[i]);
    }
  }

  const binary = findUnityBinary(unityPath);
  if (!binary) {
    process.stderr.write('Unity binary not found. Expected at:\n');
    process.stderr.write(`  ${DEFAULT_UNITY_PATH}\n`);
    process.stderr.write('Use --unity-path <path> to specify.\n');
    process.exit(1);
  }

  if (!checkNetworkNamespace()) {
    process.stderr.write('WARNING: Not running inside unitynet namespace.\n');
    process.stderr.write('Unity tests require the network namespace to avoid RakNet >10 IP crash.\n');
    process.stderr.write('Run with: sudo ip netns exec unitynet npx tsx ts/scripts/unity-runner.ts\n\n');
  }

  process.stderr.write('Loading scenarios from Python...\n');
  const scenarios = await loadScenarios();

  const names = Object.keys(scenarios).filter(
    (name) => filterArgs.length === 0 || filterArgs.some((f) => name.includes(f)),
  );

  let pass = 0;
  let fail = 0;
  let skipped = 0;
  const allResults: TestResult[] = [];

  for (const name of names) {
    process.stderr.write(`\n--- ${name} ---\n`);
    const scenario = scenarios[name];
    const runner = new UnityTestRunner(scenario, binary);
    const result = await runner.run();
    allResults.push(result);

    if (result.validation.skipped) {
      process.stderr.write(`  SKIP: ${result.validation.failures.join(', ')}\n`);
      skipped++;
    } else if (result.validation.pass) {
      process.stderr.write('  PASS\n');
      pass++;
    } else {
      process.stderr.write('  FAIL:\n');
      for (const f of result.validation.failures) {
        process.stderr.write(`    -> ${f}\n`);
      }
      fail++;
    }
  }

  process.stderr.write(`\n=== Summary: ${String(pass)} pass, ${String(fail)} fail, ${String(skipped)} skip ===\n`);
  console.log(JSON.stringify(allResults, null, 2));
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e: unknown) => {
  process.stderr.write(`Fatal: ${e instanceof Error ? e.message : String(e)}\n`);
  process.exit(2);
});
