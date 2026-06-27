/**
 * Conformance test bridge: reads M12 test JSON from stdin,
 * executes the TS implementation for each test case,
 * and writes completed JSON to stdout.
 *
 * Usage: pnpm conformance < test-cases.json
 *
 * Handlers are registered per-category in subsequent sections.
 */

import * as process from 'node:process';

type TestCase = Record<string, unknown>;

type CategoryHandler = (testCase: TestCase) => TestCase;

const handlers = new Map<string, CategoryHandler>();

export function registerHandler(category: string, handler: CategoryHandler) {
  handlers.set(category, handler);
}

async function main() {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk as Buffer);
  }
  const input = Buffer.concat(chunks).toString('utf-8').trim();

  let testCases: TestCase[];
  if (input.startsWith('[')) {
    testCases = JSON.parse(input) as TestCase[];
  } else {
    testCases = input
      .split('\n')
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line) as TestCase);
  }

  const results: TestCase[] = [];
  for (const tc of testCases) {
    const category = tc['category'] as string | undefined;
    if (!category) {
      results.push({ ...tc, error: 'missing category field' });
      continue;
    }
    const handler = handlers.get(category);
    if (!handler) {
      results.push({ ...tc, error: `no handler for category: ${category}` });
      continue;
    }
    try {
      results.push(handler(tc));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      results.push({ ...tc, error: message });
    }
  }

  console.log(JSON.stringify(results));
}

void main();
