"""Console-script entry point for spire-ui (Doc B §5.1.7).

Launches Streamlit's CLI on the sibling app.py. This module never
renders the page itself — app.py does that, when Streamlit re-executes
it with a ScriptRunContext set.

Called by:  spire-ui
      or:  python -m spire.ui
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli as stcli

    app_path = Path(__file__).resolve().parent / "app.py"
    host = os.environ.get("SPIRE_UI_HOST", "0.0.0.0")
    port = os.environ.get("SPIRE_UI_PORT", "8888")

    sys.argv = [
        "streamlit", "run", str(app_path),
        "--server.address", host,
        "--server.port", port,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()