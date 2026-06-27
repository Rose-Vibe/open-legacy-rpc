#!/usr/bin/env python3
"""
Conformance test CLI for peer (server/client interop) tests.

Usage:
  legacy-net-peer-test generate <category> <basic|random>
  legacy-net-peer-test run [--role server|client] < test.json

Exit codes:
  0 = all pass
  1 = validation failures
  2 = usage/schema error
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance.generators.peer import GENERATORS
from conformance.validators.peer import VALIDATORS


def cmd_generate(args):
    category = args.category
    mode = args.mode

    if category not in GENERATORS:
        print(f"Unknown category: {category}", file=sys.stderr)
        print(f"Available: {', '.join(sorted(GENERATORS.keys()))}", file=sys.stderr)
        return 2

    tests = GENERATORS[category](mode)
    json.dump(tests, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 0


def cmd_run(args):
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input on stdin", file=sys.stderr)
        return 2

    try:
        test_obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 2

    category = test_obj.get('testInfo', {}).get('category')
    if category not in VALIDATORS:
        print(f"Unknown peer test category: {category}", file=sys.stderr)
        return 2

    # Peer test execution will be implemented in M12c
    print("Peer test execution not yet implemented", file=sys.stderr)
    return 2


def main():
    parser = argparse.ArgumentParser(
        prog='legacy-net-peer-test',
        description='Conformance peer test generator and runner',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    gen_parser = subparsers.add_parser('generate', help='Generate test scenarios')
    gen_parser.add_argument('category', help='Test category')
    gen_parser.add_argument('mode', choices=['basic', 'random'])

    run_parser = subparsers.add_parser('run', help='Run a peer test')
    run_parser.add_argument('--role', choices=['server', 'client'],
                           default='server',
                           help='Role for the Python peer')

    list_parser = subparsers.add_parser('list', help='List available categories')

    args = parser.parse_args()

    if args.command == 'generate':
        sys.exit(cmd_generate(args))
    elif args.command == 'run':
        sys.exit(cmd_run(args))
    elif args.command == 'list':
        for name in sorted(GENERATORS.keys()):
            print(name)
        sys.exit(0)


if __name__ == '__main__':
    main()
