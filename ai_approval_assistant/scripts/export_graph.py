from __future__ import annotations

from pathlib import Path
import sys

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai_approval_assistant.app.graph.workflow import create_workflow  # noqa: E402


ROOT = PACKAGE_ROOT
OUTPUT = ROOT / "docs" / "approval_graph.mmd"


def main() -> None:
    graph = create_workflow().get_graph()
    mermaid = graph.draw_mermaid()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(mermaid, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
