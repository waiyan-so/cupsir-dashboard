"""pytest setup: make scripts/ importable the same way `python scripts/xxx.py` does.

The repo root has a config/ folder and scripts/ has a config.py module, so the
new code never does `import config`; it reads config/*.json by file path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
