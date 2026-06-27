import { MasterServer } from '../src/master/server.js';
import { MasterClient } from '../src/master/client.js';

async function main(): Promise<void> {
  const port = 24000 + Math.floor(Math.random() * 1000);
  const server = new MasterServer({ port });
  await server.start();

  const client = new MasterClient();
  await client.connect('127.0.0.1', port);

  const rowId = await client.registerHost({
    gameType: 'TestGame',
    name: 'My Test Server',
    comment: 'self-test',
    playerCount: 2,
    playerLimit: 16,
    port: 7777,
  });

  console.log('Registered with rowId:', rowId);

  const hosts = await client.requestHostList('TestGame');
  console.log('Found', hosts.length, 'host(s)');

  if (hosts.length !== 1) {
    console.error('FAIL: expected 1 host, got', hosts.length);
    process.exit(1);
  }

  const host = hosts[0];
  if (!host) {
    console.error('FAIL: host is undefined');
    process.exit(1);
  }

  const checks: Array<[string, unknown, unknown]> = [
    ['gameName', host.gameName, 'My Test Server'],
    ['comment', host.comment, 'self-test'],
    ['connectedPlayers', host.connectedPlayers, 2],
    ['playerLimit', host.playerLimit, 16],
    ['rowId', host.rowId, rowId],
  ];

  let passed = true;
  for (const [name, actual, expected] of checks) {
    if (actual !== expected) {
      console.error('FAIL:', name, '- expected', expected, 'got', actual);
      passed = false;
    }
  }

  client.unregisterHost('TestGame');
  await new Promise((r) => setTimeout(r, 200));

  const hostsAfter = await client.requestHostList('TestGame');
  if (hostsAfter.length !== 0) {
    console.error('FAIL: expected 0 hosts after unregister, got', hostsAfter.length);
    passed = false;
  }

  await client.close();
  await server.stop();

  if (passed) {
    console.log('All self-test checks passed');
  } else {
    process.exit(1);
  }
}

void main();
