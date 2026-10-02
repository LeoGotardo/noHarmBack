"""docs/CONFIGURATION.md must list every environment variable the code reads."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_configuration_reference_is_up_to_date():
    result = subprocess.run(
        [sys.executable, "scripts/gen_config_reference.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "docs/CONFIGURATION.md is stale — run "
        "`venv/bin/python scripts/gen_config_reference.py` and commit the result.\n"
        + result.stderr
    )


def test_every_variable_read_outside_config_py_is_documented():
    """A new os.environ read in src/ or in the entrypoint must land in OUTSIDE."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from gen_config_reference import OUTSIDE  # noqa: E402

    documented = set(OUTSIDE) | set(re.findall(r"`([A-Z][A-Z0-9_]+)`", (ROOT / "docs" / "CONFIGURATION.md").read_text()))
    read = set()
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "config.py":
            continue
        read |= set(re.findall(r'os\.environ(?:\.get)?\(?\[?"([A-Z][A-Z0-9_]+)"', path.read_text()))
    read |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]{2,})", (ROOT / "docker" / "entrypoint.sh").read_text()))
    missing = sorted(read - documented)
    assert not missing, f"read by the code but not in docs/CONFIGURATION.md: {missing}"
