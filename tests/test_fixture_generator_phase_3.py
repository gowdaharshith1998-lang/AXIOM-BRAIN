from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_fixture_generator_is_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).parent.parent
    fixture_path = repo_root / "fixtures" / "synthetic_company.json"

    # Run generator twice; file bytes must match.
    subprocess.run(["python", "scripts/generate_fixture.py"], cwd=repo_root, check=True)
    h1 = _sha256(fixture_path)
    subprocess.run(["python", "scripts/generate_fixture.py"], cwd=repo_root, check=True)
    h2 = _sha256(fixture_path)
    assert h1 == h2
