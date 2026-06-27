#!/usr/bin/env python3
"""
Conformance test CLI for serde (encode/decode) tests.

Usage:
  legacy-net-serde-test generate <category> <basic|random> [--count N] [--seed S]
  legacy-net-serde-test validate < responses.json

Exit codes:
  0 = all pass (or successful generation)
  1 = one or more validation failures
  2 = usage/schema error
"""

import argparse
import json
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance.generators.serde import GENERATORS
from conformance.validators.serde import VALIDATORS


def cmd_generate(args):
    category = args.category
    mode = args.mode

    if category not in GENERATORS:
        print(f"Unknown category: {category}", file=sys.stderr)
        print(f"Available: {', '.join(sorted(GENERATORS.keys()))}", file=sys.stderr)
        return 2

    rng = random.Random(args.seed) if args.seed is not None else None
    tests = GENERATORS[category](mode, count=args.count, rng=rng)
    json.dump(tests, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 0


def cmd_validate(args):
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input on stdin", file=sys.stderr)
        return 2

    # Support both JSON array and newline-delimited JSON
    if raw.startswith('['):
        try:
            test_objects = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON array: {e}", file=sys.stderr)
            return 2
    else:
        test_objects = []
        for line_num, line in enumerate(raw.split('\n'), 1):
            line = line.strip()
            if not line:
                continue
            try:
                test_objects.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Invalid JSON on line {line_num}: {e}", file=sys.stderr)
                return 2

    results = []
    any_failures = False

    for obj in test_objects:
        category = obj.get('testInfo', {}).get('category')
        if category not in VALIDATORS:
            result = dict(obj)
            result['validation'] = {
                'pass': False,
                'failures': [f"Unknown category: {category}"],
            }
            results.append(result)
            any_failures = True
            continue

        validation = VALIDATORS[category](obj)
        result = dict(obj)
        result['validation'] = validation
        results.append(result)
        if not validation['pass']:
            any_failures = True

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 1 if any_failures else 0


def main():
    parser = argparse.ArgumentParser(
        prog='legacy-net-serde-test',
        description='Conformance serde test generator and validator',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    gen_parser = subparsers.add_parser('generate', help='Generate test cases')
    gen_parser.add_argument('category', help='Test category')
    gen_parser.add_argument('mode', choices=['basic', 'random'],
                           help='basic (preset) or random')
    gen_parser.add_argument('--count', type=int, default=10,
                           help='Number of random tests (default: 10)')
    gen_parser.add_argument('--seed', type=int, default=None,
                           help='Random seed for reproducibility')

    subparsers.add_parser('validate',
                          help='Validate test responses from stdin')

    list_parser = subparsers.add_parser('list', help='List available categories')

    args = parser.parse_args()

    if args.command == 'generate':
        sys.exit(cmd_generate(args))
    elif args.command == 'validate':
        sys.exit(cmd_validate(args))
    elif args.command == 'list':
        for name in sorted(GENERATORS.keys()):
            print(name)
        sys.exit(0)


if __name__ == '__main__':
    main()
