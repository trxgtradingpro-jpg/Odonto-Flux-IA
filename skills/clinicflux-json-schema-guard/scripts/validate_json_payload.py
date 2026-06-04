"""Strict JSON payload validator for ClinicFlux skill workflows.

Reads one or more files, or '-' for stdin. Fails when the input is not a single
strict JSON value. By default the top-level value must be an object or array.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def _validate_json(source: str, text: str, allow_scalar: bool) -> tuple[bool, str]:
    stripped = text.strip()
    if not stripped:
        return False, f"{source}: empty input"

    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        return False, f"{source}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"

    trailing = stripped[end:].strip()
    if trailing:
        return False, f"{source}: extra text after JSON value"

    if not allow_scalar and not isinstance(value, (dict, list)):
        return False, f"{source}: top-level JSON must be object or array"

    return True, f"{source}: valid {type(value).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate strict JSON payloads.")
    parser.add_argument("sources", nargs="+", help="JSON files to validate, or '-' for stdin")
    parser.add_argument("--allow-scalar", action="store_true", help="Allow string/number/boolean/null top-level JSON")
    args = parser.parse_args(argv)

    exit_code = 0
    for source in args.sources:
        try:
            text = _read_source(source)
        except OSError as exc:
            print(f"{source}: could not read: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        ok, message = _validate_json(source, text, args.allow_scalar)
        print(message, file=sys.stdout if ok else sys.stderr)
        if not ok:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
