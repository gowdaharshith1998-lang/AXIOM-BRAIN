from pathlib import Path

DESIGN_PATH = Path(__file__).parent.parent / "DESIGN.md"

REQUIRED_SECTIONS = [
    "Vision and architecture",
    "Entity schema",
    "Edge schema",
    "Receipt schema",
    "Source ABC",
    "MCP tool surface",
    "Policy YAML schema",
    "Skills emitter output",
    "WebSocket message types",
    "Hosting topology",
    "Database schema",
    "Directory structure",
    "Phase-by-phase contract checklist",
    "Open questions for dispatcher",
]


def test_design_doc_exists():
    assert DESIGN_PATH.exists(), "DESIGN.md must exist in repo root"


def test_design_doc_has_required_sections():
    content = DESIGN_PATH.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in content, f"Missing required section: {section}"


def test_design_doc_no_omnix_terminology():
    content = DESIGN_PATH.read_text(encoding="utf-8").lower()
    forbidden = ["omnix", "x-ray", "xray", "constellation", "code intelligence"]
    for term in forbidden:
        assert term not in content, f"Found forbidden term: {term}"


def test_design_doc_uses_axiom_naming():
    content = DESIGN_PATH.read_text(encoding="utf-8")
    assert "AXIOM" in content
    assert "Calibra" in content
    assert "AXIOM-BRAIN" in content
