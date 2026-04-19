from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_required_docs_pin_deterministic_router_before_classifier():
    required_order = "pending -> instant -> skills -> deterministic router -> classifier"

    docs = {
        ".CODEX/AGENTS.md": _read(".CODEX/AGENTS.md"),
        ".CODEX/Codex.md": _read(".CODEX/Codex.md"),
        "docs/phases/PHASE.md": _read("docs/phases/PHASE.md"),
        "docs/phases/PHASE_PROGRESS.md": _read("docs/phases/PHASE_PROGRESS.md"),
    }

    for path, text in docs.items():
        assert "deterministic router" in text, f"{path} must mention the deterministic router step"
        assert required_order in text, f"{path} must pin deterministic router before classifier"


def test_codex_routing_flow_does_not_send_skills_directly_to_classifier():
    text = _read(".CODEX/Codex.md")
    flow_start = text.index("## ROUTING FLOW")
    flow_end = text.index("## MODELS", flow_start)
    flow = text[flow_start:flow_end]

    assert "6.  high-confidence deterministic router match" in flow
    assert "7.  config-driven classifier fallback" in flow
    assert "6.  config-driven classifier" not in flow
