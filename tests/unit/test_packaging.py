import subprocess
import sys

import forgex
from forgex.prompts import PROMPT_VERSIONS, load_prompt


def test_version_is_defined():
    assert isinstance(forgex.__version__, str)
    assert len(forgex.__version__.split(".")) >= 3


def test_console_entry_point_is_callable():
    from forgex.cli.app import main

    assert callable(main)


def test_all_registered_prompts_ship_and_load():
    """Catches a prompt .md that was registered but never added — before it
    ships in a wheel (packaging regression guard)."""
    assert PROMPT_VERSIONS, "no prompts registered"
    for name in PROMPT_VERSIONS:
        text = load_prompt(name)
        assert text.strip(), f"prompt {name} is empty or missing from package data"


def test_module_entry_point_version():
    result = subprocess.run([sys.executable, "-m", "forgex", "--version"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
