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

async function runPythonPeer(scenario: Scenario, port: number): Promise<TestResult> {
  const scenarioWithPort = { ...scenario, port };
  return runSubprocess(
    'python3',
    ['-c', `
import json, sys
sys.path.insert(0, '.')
from conformance.peer_runner import PeerTestRunner

scenario = json.loads(sys.stdin.read())
port = scenario.pop('port', 18800)
runner = PeerTestRunner(scenario)
runner.port = port
result = runner.run()
json.dump(result, sys.stdout)
`],
    JSON.stringify(scenarioWithPort),
    PROJECT_ROOT,
  );
}

async function runTsPeer(scenario: Scenario, port: number): Promise<TestResult> {
  const scenarioWithPort = { ...scenario, port };
  const output = await runSubprocessRaw(
    'npx',
    ['tsx', 'ts/scripts/peer-runner.ts'],
    JSON.stringify([scenarioWithPort]),
    PROJECT_ROOT,
  );
  try {
    const results = JSON.parse(output) as TestResult[];
    return results[0] ?? { testInfo: scenario.testInfo, mode: '', validation: { pass: false, failures: ['No result'] } };
  } catch {
    return { testInfo: scenario.testInfo, mode: '', validation: { pass: false, failures: [`Parse error: ${output.slice(0, 200)}`] } };
  }
}

function runSubprocessRaw(
  cmd: string,
  args: string[],
  stdin: string,
  cwd: string,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { cwd, timeout: 15000 });
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

async function runSubprocess(
  cmd: string,
  args: string[],
  stdin: string,
  cwd: string,
): Promise<TestResult> {
  const output = await runSubprocessRaw(cmd, args, stdin, cwd);
  try {
    return JSON.parse(output) as TestResult;
  } catch {
    return {
      testInfo: { testId: '', testName: 'unknown', testDescription: '', category: '', mode: '' },
      mode: '',
      validation: { pass: false, failures: [`Parse error: ${output.slice(0, 200)}`] },
    };
  }
}

let portCounter = 20800;
function nextPort(): number {
  return ++portCounter;
}

async function main(): Promise<void> {
  const categories = process.argv.slice(2);
  const cats = categories.length > 0 ? categories : CATEGORIES;

  const allResults: TestResult[] = [];
  let totalPass = 0;
  let totalFail = 0;

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
      // TS-as-both-sides
      const port = nextPort();
      const result = await runTsPeer(scenario, port);
      result.mode = 'ts-both';
      allResults.push(result);

      const status = result.validation.pass ? 'PASS' : 'FAIL';
      process.stderr.write(`  ${status}: ${scenario.testInfo.testName} [ts-both]\n`);
      if (result.validation.pass) {
        totalPass++;
      } else {
        totalFail++;
        for (const f of result.validation.failures) {
          process.stderr.write(`    -> ${f}\n`);
        }
      }

      // Python-as-both-sides (baseline)
      const port2 = nextPort();
      const pyResult = await runPythonPeer(scenario, port2);
      pyResult.mode = 'py-both';
      allResults.push(pyResult);

      const pyStatus = pyResult.validation.pass ? 'PASS' : 'FAIL';
      process.stderr.write(`  ${pyStatus}: ${scenario.testInfo.testName} [py-both]\n`);
      if (pyResult.validation.pass) {
        totalPass++;
      } else {
        totalFail++;
        for (const f of pyResult.validation.failures) {
          process.stderr.write(`    -> ${f}\n`);
        }
      }
    }
  }

  process.stderr.write(`\n=== Summary: ${String(totalPass)} pass, ${String(totalFail)} fail ===\n`);
  console.log(JSON.stringify(allResults, null, 2));
  process.exit(totalFail > 0 ? 1 : 0);
}

main().catch((e: unknown) => {
  process.stderr.write(`Fatal: ${e instanceof Error ? e.message : String(e)}\n`);
  process.exit(2);
});
