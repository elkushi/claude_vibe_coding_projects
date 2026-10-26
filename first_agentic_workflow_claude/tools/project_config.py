"""Load project.json, the per-company settings that make the workflow reusable.

project.json is private (gitignored): your company name, names that must never
appear in a report, and market-specific checks. project.example.json is the
public template; copy it to project.json and fill it in. If project.json is
missing, the example is used and a warning is printed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load() -> dict:
    path = ROOT / "project.json"
    if not path.exists():
        print("WARN: project.json not found, using project.example.json "
              "(copy it to project.json and fill in your company)", file=sys.stderr)
        path = ROOT / "project.example.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.setdefault("forbidden_terms", [])
    cfg.setdefault("market", {})
    return cfg
