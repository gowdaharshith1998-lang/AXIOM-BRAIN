from __future__ import annotations

import re
from pathlib import Path


def test_no_calibra_imports_in_src_or_frontend() -> None:
    # Calibra is Phase 7; Phase 3 must not import it.
    repo = Path(__file__).parent.parent
    roots = [repo / "src", repo / "frontend" / "src"]
    pat = re.compile(r"^\s*(import\s+calibra\b|from\s+calibra\b)", re.IGNORECASE)
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in {".py", ".ts", ".tsx"}:
                continue
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if pat.search(line):
                    hits.append(f"{p}:{line}")
                    break
    assert hits == [], "Found calibra imports:\n" + "\n".join(hits)


def test_no_type_string_branches_in_phase_3_python() -> None:
    # Universal-entity discipline: no `if x.type == "..."` branches in Phase 3 code.
    repo = Path(__file__).parent.parent
    roots = [
        repo / "src" / "axiom" / "sources",
        repo / "src" / "axiom" / "ingest",
        repo / "src" / "axiom" / "studio",
    ]
    pat = re.compile(r"^\s*if\s+.*\.type\s*==\s*['\"]", re.IGNORECASE)
    hits: list[str] = []
    for root in roots:
        for p in root.rglob("*.py"):
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines, start=1):
                if pat.search(line):
                    hits.append(f"{p}:{i}:{line}")
    assert hits == [], "Found type-string branches:\n" + "\n".join(hits)
