#!/usr/bin/env python3
"""
Conformance test CLI for peer (server/client interop) tests.

Usage:
  legacy-net-peer-test generate <category> <basic|random>
  legacy-net-peer-test run < test.json
  legacy-net-peer-test unity <scenario> [--unity-path PATH]
  legacy-net-peer-test list [--unity]

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
from conformance.peer_runner import run_scenario


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
        scenarios = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 2

    if isinstance(scenarios, dict):
        scenarios = [scenarios]

    any_fail = False
    results = []
    for scenario in scenarios:
        result = run_scenario(scenario)
        results.append(result)
        if not result['validation']['pass']:
            any_fail = True

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 1 if any_fail else 0


def cmd_unity(args):
    from conformance.generators.unity.scenarios import get_scenario, list_scenarios
    from conformance.unity_runner import run_unity_scenario, find_unity_binary

    if args.scenario == 'all':
        scenario_names = list_scenarios()
    else:
        scenario_names = [args.scenario]

    unity_path = find_unity_binary(args.unity_path)
    if not unity_path:
        print("Unity binary not found. Use --unity-path to specify.", file=sys.stderr)
        return 2

    any_fail = False
    results = []
    for name in scenario_names:
        try:
            scenario = get_scenario(name)
        except KeyError:
            print(f"Unknown scenario: {name}", file=sys.stderr)
            print(f"Available: {', '.join(list_scenarios())}", file=sys.stderr)
            return 2

        result = run_unity_scenario(scenario, unity_path=unity_path,
                                    timeout=args.timeout)
        results.append(result)
        status = 'PASS' if result['validation']['pass'] else 'FAIL'
        print(f"{status}: {name}", file=sys.stderr)
        if not result['validation']['pass']:
            any_fail = True
            for f in result['validation']['failures']:
                print(f"  -> {f}", file=sys.stderr)

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 1 if any_fail else 0


def main():
    parser = argparse.ArgumentParser(
        prog='legacy-net-peer-test',
        description='Conformance peer test generator and runner',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    gen_parser = subparsers.add_parser('generate', help='Generate test scenarios')
    gen_parser.add_argument('category', help='Test category')
    gen_parser.add_argument('mode', choices=['basic', 'random'])

    run_parser = subparsers.add_parser('run', help='Run a peer test scenario')

    unity_parser = subparsers.add_parser('unity', help='Run a Unity test scenario')
    unity_parser.add_argument('scenario', help='Scenario name or "all"')
    unity_parser.add_argument('--unity-path', help='Path to Unity binary')
    unity_parser.add_argument('--timeout', type=float, default=15.0,
                             help='Timeout in seconds')

    list_parser = subparsers.add_parser('list', help='List available categories')
    list_parser.add_argument('--unity', action='store_true',
                            help='List Unity scenarios instead of peer categories')

    args = parser.parse_args()

    if args.command == 'generate':
        sys.exit(cmd_generate(args))
    elif args.command == 'run':
        sys.exit(cmd_run(args))
    elif args.command == 'unity':
        sys.exit(cmd_unity(args))
    elif args.command == 'list':
        if args.unity:
            from conformance.generators.unity.scenarios import list_scenarios
            for name in list_scenarios():
                print(name)
        else:
            for name in sorted(GENERATORS.keys()):
                print(name)
        sys.exit(0)


if __name__ == '__main__':
    main()
