"""Fill the Homebrew formula template from a version published on PyPI.

    python scripts/make_formula.py 1.0.1 --license MIT > Formula/stackloom.rb
    brew update-python-resources --exclude-packages numpy Formula/stackloom.rb

Reads https://pypi.org/pypi/stackloom/<version>/json for the sdist URL and SHA-256.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "packaging" / "homebrew" / "stackloom.rb.template"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--license", required=True, help="SPDX id of the licence STACKLOOM is released under")
    args = parser.parse_args()
    with urllib.request.urlopen(f"https://pypi.org/pypi/stackloom/{args.version}/json", timeout=20) as response:
        data = json.load(response)
    sdist = next((f for f in data["urls"] if f["packagetype"] == "sdist"), None)
    if sdist is None:
        print(f"stackloom {args.version} has no sdist on PyPI", file=sys.stderr)
        return 1
    text = TEMPLATE.read_text().replace("@URL@", sdist["url"]).replace("@SHA256@", sdist["digests"]["sha256"])
    sys.stdout.write(text.replace("@LICENSE@", args.license))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
