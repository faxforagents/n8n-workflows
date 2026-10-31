#!/usr/bin/env python3
"""Check every workflows/*.json: valid JSON, n8n shape, every connection names a node, no credential or key.

Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_RE = re.compile(r"ffa_(test|live)_[A-Za-z0-9_-]{8,}")


def main() -> int:
    problems: list[str] = []
    paths = sorted(ROOT.glob("workflows/*.json"))
    if not paths:
        problems.append("no workflows/*.json")
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        try:
            wf = json.loads(raw)
        except json.JSONDecodeError as err:
            problems.append(f"{path.name}: not JSON: {err}")
            continue
        for field in ("name", "nodes", "connections", "settings"):
            if field not in wf:
                problems.append(f"{path.name}: {field} is missing")
        names = {n.get("name") for n in wf.get("nodes", [])}
        for n in wf.get("nodes", []):
            for field in ("id", "name", "type", "typeVersion", "position", "parameters"):
                if field not in n:
                    problems.append(f"{path.name}: node {n.get('name')!r} has no {field}")
            if "credentials" in n:
                problems.append(f"{path.name}: node {n.get('name')!r} carries a credential reference")
        for source, conn in wf.get("connections", {}).items():
            if source not in names:
                problems.append(f"{path.name}: connection from unknown node {source!r}")
            for outputs in conn.get("main", []):
                for target in outputs:
                    if target.get("node") not in names:
                        problems.append(f"{path.name}: connection to unknown node {target.get('node')!r}")
        if KEY_RE.search(raw.replace("ffa_test_...", "")):
            problems.append(f"{path.name}: an API key is in the file")
    # the committed JSON must be what the builder writes
    builder = ROOT / "scripts" / "build_workflow.py"
    before = {p: p.read_bytes() for p in paths}
    subprocess.run([sys.executable, str(builder)], check=True, capture_output=True)
    for p, content in before.items():
        if p.read_bytes() != content:
            problems.append(f"{p.name}: differs from what scripts/build_workflow.py writes, run it and commit")
    for problem in problems:
        print(f"check_workflow: FAIL: {problem}", file=sys.stderr)
    if not problems:
        print(f"check_workflow: OK ({len(paths)} workflow)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
