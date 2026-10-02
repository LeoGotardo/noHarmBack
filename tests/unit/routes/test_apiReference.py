"""docs/API.md is generated from the app; it must match the routes as they are."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_api_reference_is_up_to_date():
    result = subprocess.run(
        [sys.executable, "scripts/gen_api_reference.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "docs/API.md no longer matches the routes — run "
        "`venv/bin/python scripts/gen_api_reference.py` and commit the result.\n"
        + result.stderr
    )
