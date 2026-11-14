#!/usr/bin/env python3
"""Entry point.

Reads one JSON document {"schema": <SDL>, "query": <str>, "root": <obj>}
from a file argument or stdin, and prints {"data": ..., "errors": [...]}.

With a second argument the result is written to that file -- but only when
the request was accepted: on success the output file is replaced, on
rejection the old file is kept untouched. The result is always printed to
stdout. Exit code is 0 when the request was accepted (field errors still
produce a result), 1 when it was rejected, 2 on usage/IO errors.
"""

import json
import sys
from pathlib import Path

from backend.service import run_request


def _load(text: str):
    """Parse JSON, rejecting duplicate object members."""

    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate member: {key!r}")
            obj[key] = value
        return obj

    return json.loads(text, object_pairs_hook=no_duplicates)


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("usage: main.py [input.json] [output.json]", file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text(encoding="utf-8") if argv else sys.stdin.read()
    except OSError as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2

    try:
        payload = _load(text)
    except ValueError:
        output, accepted = {"data": None, "errors": [["$"]]}, False
    else:
        output, accepted = run_request(payload)

    line = json.dumps(output, ensure_ascii=False)
    print(line)
    if len(argv) == 2 and accepted:
        Path(argv[1]).write_text(line + "\n", encoding="utf-8")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
