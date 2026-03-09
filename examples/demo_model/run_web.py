"""Start the Explicator web UI wired to the demo bond portfolio model.

Run with:
    cd examples/demo_model
    uv run run_web.py

Then open http://localhost:8000 in your browser.
Requires an AI provider key (e.g. ANTHROPIC_API_KEY in .env or environment).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import explicator
from model import build_service

if __name__ == "__main__":
    service = build_service()
    explicator.run_web(service)
