import * as process from 'node:process';
import { spawn } from 'node:child_process';

interface TestInfo {
  testId: string;
  testName: string;
  testDescription: string;
  category: string;
  mode: string;
}

interface Scenario {
  testInfo: TestInfo;
  steps: Array<{ action: string; [key: string]: unknown }>;
}

interface TestResult {
  testInfo: TestInfo;
  mode: string;
  validation: {
    pass: boolean;
    failures: string[];
  };
}

const CATEGORIES = ['handshake', 'rpc', 'stateSync', 'multiClient', 'edgeCases'];
const PROJECT_ROOT = new URL('../../', import.meta.url).pathname.replace(/\/$/, '');
const TSX = new URL('../../ts/node_modules/.bin/tsx', import.meta.url).pathname;

async function generateScenarios(category: string): Promise<Scenario[]> {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', ['-m', 'conformance.peer_test_cli', 'generate', category, 'basic'], {
      cwd: PROJECT_ROOT,
    });
    const chunks: Buffer[] = [];
    proc.stdout.on('data', (chunk: Buffer) => {
      chunks.push(chunk);
    });
    proc.stderr.on('data', (chunk: Buffer) => {
      process.stderr.write(chunk);
    });
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`generate ${category} exited with code ${String(code)}`));
        return;
      }
      try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString()) as Scenario[];
        resolve(parsed);
      } catch (e: unknown) {
        reject(new Error(`Failed to parse scenarios: ${e instanceof Error ? e.message : String(e)}`));
      }
    });
  });
}

function runSubprocessRaw(
  cmd: string,
  args: string[],
  stdin: string,
  cwd: string,
  timeoutMs = 30000,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { cwd, timeout: timeoutMs });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    proc.stdout.on('data', (chunk: Buffer) => {
      stdout.push(chunk);
    });
    proc.stderr.on('data', (chunk: Buffer) => {
      stderr.push(chunk);
    });
    proc.on('close', () => {
      resolve(Buffer.concat(stdout).toString());
    });
    proc.on('error', reject);
    proc.stdin.write(stdin);
    proc.stdin.end();
  });
}

function parseTsResult(output: string, scenario: Scenario): TestResult {
  try {
    const results = JSON.parse(output) as TestResult[];
    return results[0] ?? { testInfo: scenario.testInfo, mode: '', validation: { pass: false, failures: ['No result'] } };
  } catch {
    return { testInfo: scenario.testInfo, mode: '', validation: { pass: false, failures: [`Parse error: ${output.slice(0, 200)}`] } };
  }
}

function parsePyResult(output: string, scenario: Scenario): TestResult {
  try {
    const parsed: unknown = JSON.parse(output);
    if (Array.isArray(parsed)) {
      return (parsed as TestResult[])[0] ?? { testInfo: scenario.testInfo, mode: '', validation: { pass: false, failures: ['No result'] } };
    }
    return parsed as TestResult;
  } catch {
    return {
      testInfo: scenario.testInfo,
      mode: '',
      validation: { pass: false, failures: [`Parse error: ${output.slice(0, 200)}`] },
    };
  }
}

async function runTsBoth(scenario: Scenario, port: number): Promise<TestResult> {
  const scenarioWithPort = { ...scenario, port };
  const output = await runSubprocessRaw(
    TSX, ['ts/scripts/peer-runner.ts'],
    JSON.stringify([scenarioWithPort]), PROJECT_ROOT,
  );
  return parseTsResult(output, scenario);
}

async function runPyBoth(scenario: Scenario, port: number): Promise<TestResult> {
  const scenarioWithPort = { ...scenario, port };
  const output = await runSubprocessRaw(
    'python3', ['-m', 'conformance.peer_test_cli', 'run'],
    JSON.stringify(scenarioWithPort), PROJECT_ROOT,
  );
  return parsePyResult(output, scenario);
}

async function runCrossLanguage(
  scenario: Scenario,
  port: number,
  mode: 'ts-server/py-client' | 'py-server/ts-client',
): Promise<TestResult> {
  const scenarioWithPort = { ...scenario, port };
  const scenarioJson = JSON.stringify(scenarioWithPort);
  const scenarioArrayJson = JSON.stringify([scenarioWithPort]);

  let serverProc: ReturnType<typeof spawn>;
  let clientProc: ReturnType<typeof spawn>;

  if (mode === 'ts-server/py-client') {
    serverProc = spawn(TSX, ['ts/scripts/peer-runner.ts', '--role', 'server'], {
      cwd: PROJECT_ROOT, timeout: 30000,
    });
    clientProc = spawn('python3', ['-m', 'conformance.peer_test_cli', 'run', '--role', 'client'], {
      cwd: PROJECT_ROOT, timeout: 30000,
    });
    serverProc.stdin.write(scenarioArrayJson);
    serverProc.stdin.end();
    clientProc.stdin.write(scenarioJson);
    clientProc.stdin.end();
  } else {
    serverProc = spawn('python3', ['-m', 'conformance.peer_test_cli', 'run', '--role', 'server'], {
      cwd: PROJECT_ROOT, timeout: 30000,
    });
    clientProc = spawn(TSX, ['ts/scripts/peer-runner.ts', '--role', 'client'], {
      cwd: PROJECT_ROOT, timeout: 30000,
    });
    serverProc.stdin.write(scenarioJson);
    serverProc.stdin.end();
    clientProc.stdin.write(scenarioArrayJson);
    clientProc.stdin.end();
  }

  const collectOutput = (proc: ReturnType<typeof spawn>): Promise<{ stdout: string; stderr: string; code: number | null }> =>
    new Promise((resolve) => {
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      proc.stdout?.on('data', (chunk: Buffer) => {
        stdout.push(chunk);
      });
      proc.stderr?.on('data', (chunk: Buffer) => {
        stderr.push(chunk);
      });
      proc.on('close', (code) => {
        resolve({
          stdout: Buffer.concat(stdout).toString(),
          stderr: Buffer.concat(stderr).toString(),
          code,
        });
      });
      proc.on('error', () => {
        resolve({ stdout: '', stderr: 'Process error', code: -1 });
      });
    });

  const [serverResult, clientResult] = await Promise.all([
    collectOutput(serverProc),
    collectOutput(clientProc),
  ]);

  const failures: string[] = [];

  const isTs = mode === 'ts-server/py-client';
  const serverOut = isTs
    ? parseTsResult(serverResult.stdout, scenario)
    : parsePyResult(serverResult.stdout, scenario);
  const clientOut = isTs
    ? parsePyResult(clientResult.stdout, scenario)
    : parseTsResult(clientResult.stdout, scenario);

  if (!serverOut.validation.pass) {
    failures.push(...serverOut.validation.failures.map((f) => `server: ${f}`));
  }
  if (!clientOut.validation.pass) {
    failures.push(...clientOut.validation.failures.map((f) => `client: ${f}`));
  }

  if (failures.length === 0 && (serverResult.code !== 0 || clientResult.code !== 0)) {
    if (serverResult.code !== 0) {
      failures.push(`Server (${mode.split('/')[0]}) exited ${String(serverResult.code)}: ${serverResult.stderr.slice(0, 200)}`);
    }
    if (clientResult.code !== 0) {
      failures.push(`Client (${mode.split('/')[1]}) exited ${String(clientResult.code)}: ${clientResult.stderr.slice(0, 200)}`);
    }
  }

  return {
    testInfo: scenario.testInfo,
    mode,
    validation: { pass: failures.length === 0, failures },
  };
}

let portCounter = 20800;
function nextPort(): number {
  return ++portCounter;
}

type Mode = 'ts-both' | 'py-both' | 'ts-server/py-client' | 'py-server/ts-client';

function logResult(result: TestResult, totalPass: { v: number }, totalFail: { v: number }): void {
  const status = result.validation.pass ? 'PASS' : 'FAIL';
  process.stderr.write(`  ${status}: ${result.testInfo.testName} [${result.mode}]\n`);
  if (result.validation.pass) {
    totalPass.v++;
  } else {
    totalFail.v++;
    for (const f of result.validation.failures) {
      process.stderr.write(`    -> ${f}\n`);
    }
  }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const modeFlags: Mode[] = [];
  const catArgs: string[] = [];

  for (const arg of args) {
    if (arg === '--cross' || arg === '--cross-language') {
      modeFlags.push('ts-server/py-client', 'py-server/ts-client');
    } else if (arg === '--all') {
      modeFlags.push('ts-both', 'py-both', 'ts-server/py-client', 'py-server/ts-client');
    } else if (arg === '--parity') {
      modeFlags.push('ts-both', 'py-both');
    } else if (!arg.startsWith('-')) {
      catArgs.push(arg);
    }
  }

  const modes: Mode[] = modeFlags.length > 0 ? modeFlags : ['ts-both', 'py-both', 'ts-server/py-client', 'py-server/ts-client'];
  const cats = catArgs.length > 0 ? catArgs : CATEGORIES;

  const allResults: TestResult[] = [];
  const totalPass = { v: 0 };
  const totalFail = { v: 0 };

  for (const cat of cats) {
    process.stderr.write(`\n=== ${cat} ===\n`);
    let scenarios: Scenario[];
    try {
      scenarios = await generateScenarios(cat);
    } catch (e: unknown) {
      process.stderr.write(`Failed to generate ${cat}: ${e instanceof Error ? e.message : String(e)}\n`);
      continue;
    }

    for (const scenario of scenarios) {
      for (const mode of modes) {
        const port = nextPort();
        let result: TestResult;

        if (mode === 'ts-both') {
          result = await runTsBoth(scenario, port);
          result.mode = 'ts-both';
        } else if (mode === 'py-both') {
          result = await runPyBoth(scenario, port);
          result.mode = 'py-both';
        } else {
          result = await runCrossLanguage(scenario, port, mode);
        }

        allResults.push(result);
        logResult(result, totalPass, totalFail);
      }
    }
  }

  process.stderr.write(`\n=== Summary: ${String(totalPass.v)} pass, ${String(totalFail.v)} fail ===\n`);
  console.log(JSON.stringify(allResults, null, 2));
  process.exit(totalFail.v > 0 ? 1 : 0);
}

main().catch((e: unknown) => {
  process.stderr.write(`Fatal: ${e instanceof Error ? e.message : String(e)}\n`);
  process.exit(2);
});
