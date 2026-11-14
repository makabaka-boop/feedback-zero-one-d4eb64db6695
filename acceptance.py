#!/usr/bin/env python3
"""Acceptance suite.

1. Legal intersection: every case is executed both by this backend and by the
   reference library (graphql-core's executor); data and error paths must
   match exactly.
2. Extra rules: restrictions and backend-specific behavior are verified
   independently against exact expected outputs.
3. Entry point: file/stdin behavior, exit codes, and the rule that a rejected
   request keeps the old output file while an accepted one replaces it.

On full success the golden output file is replaced; on any failure it is left
untouched and the exit code is non-zero.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from graphql import build_schema, graphql_sync  # noqa: E402

from backend.service import handle_request  # noqa: E402
from tests.cases_extra import EXTRA_CASES  # noqa: E402
from tests.cases_intersection import INTERSECTION_CASES  # noqa: E402
from tests.fuzz import generate_fuzz_cases  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "results.json"


def reference_execute(sdl, query, root):
    """The reference library: graphql-core's own validator and executor."""
    schema = build_schema(sdl)
    result = graphql_sync(schema, query, root_value=root)
    return {
        "data": result.data,
        "errors": [list(error.path) for error in result.errors or []],
    }


def check_intersection():
    failures = []
    results = {}
    cases = list(INTERSECTION_CASES) + generate_fuzz_cases()
    for name, sdl, query, root in cases:
        mine = handle_request({"schema": sdl, "query": query, "root": root})
        expected = reference_execute(sdl, query, root)
        results[f"intersection/{name}"] = mine
        if mine != expected:
            failures.append((f"intersection/{name}", expected, mine))
    return failures, results, len(cases)


def check_extra():
    failures = []
    results = {}
    for name, payload, expected in EXTRA_CASES:
        mine = handle_request(payload)
        results[f"extra/{name}"] = mine
        if mine != expected:
            failures.append((f"extra/{name}", expected, mine))
    return failures, results


def check_entry():
    failures = []
    main_py = ROOT / "main.py"
    accepted_payload = {
        "schema": "type Query { a: [Int!] }",
        "query": "{ z: a }",
        "root": {"a": [None]},
    }
    accepted_output = {"data": {"z": None}, "errors": [["z", 0]]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_file = tmp / "in.json"
        out_file = tmp / "out.json"

        def run(payload_text):
            in_file.write_text(payload_text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(main_py), str(in_file), str(out_file)],
                capture_output=True, text=True, cwd=ROOT,
            )

        # 1. accepted request: exit 0, stdout carries the result, file replaced
        out_file.write_text("OLD\n", encoding="utf-8")
        proc = run(json.dumps(accepted_payload))
        if proc.returncode != 0:
            failures.append(("entry/accepted-exit-code", 0, proc.returncode))
        if json.loads(proc.stdout) != accepted_output:
            failures.append(("entry/accepted-stdout", accepted_output, proc.stdout))
        if json.loads(out_file.read_text(encoding="utf-8")) != accepted_output:
            failures.append(("entry/accepted-file-replaced", accepted_output,
                             out_file.read_text(encoding="utf-8")))

        # 2. rejected request: exit 1, stdout carries the rejection, old file kept
        out_file.write_text("OLD\n", encoding="utf-8")
        proc = run(json.dumps({"schema": "type Query { a: String }",
                               "query": "{ a", "root": {}}))
        if proc.returncode != 1:
            failures.append(("entry/rejected-exit-code", 1, proc.returncode))
        if json.loads(proc.stdout) != {"data": None, "errors": [["$"]]}:
            failures.append(("entry/rejected-stdout", [["$"]], proc.stdout))
        if out_file.read_text(encoding="utf-8") != "OLD\n":
            failures.append(("entry/rejected-file-kept", "OLD",
                             out_file.read_text(encoding="utf-8")))

        # 3. duplicate JSON members are rejected
        proc = run('{"schema": "type Query { a: String }", "query": "{ a }",'
                   ' "root": {}, "root": {}}')
        if proc.returncode != 1 or json.loads(proc.stdout) != {
            "data": None, "errors": [["$"]]
        }:
            failures.append(("entry/duplicate-member-rejected",
                             '{"data": null, "errors": [["$"]]}', proc.stdout))

        # 4. stdin mode
        proc = subprocess.run(
            [sys.executable, str(main_py)], input=json.dumps(accepted_payload),
            capture_output=True, text=True, cwd=ROOT,
        )
        if proc.returncode != 0 or json.loads(proc.stdout) != accepted_output:
            failures.append(("entry/stdin", accepted_output, proc.stdout))
    return failures


def main():
    failures = []
    results = {}

    intersection_failures, intersection_results, intersection_count = (
        check_intersection()
    )
    failures += intersection_failures
    results.update(intersection_results)

    extra_failures, extra_results = check_extra()
    failures += extra_failures
    results.update(extra_results)

    failures += check_entry()

    total = intersection_count + len(EXTRA_CASES) + 4
    if failures:
        print(f"ACCEPTANCE FAILED: {len(failures)} of {total} checks failed; "
              "golden output left untouched.")
        for name, expected, got in failures:
            print(f"\n--- {name}")
            print(f"  expected: {json.dumps(expected, ensure_ascii=False, default=str)}")
            print(f"  got:      {json.dumps(got, ensure_ascii=False, default=str)}")
        return 1

    # full success: replace the golden output
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"ACCEPTANCE PASSED: {total} checks "
          f"({intersection_count} intersection vs reference library "
          f"[incl. seeded fuzz], {len(EXTRA_CASES)} extra rules, "
          f"4 entry-point). Golden output replaced: "
          f"{GOLDEN.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
