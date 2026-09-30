import sys
from pathlib import Path

_base = Path(__file__).resolve().parent
if str(_base) not in sys.path:
    sys.path.insert(0, str(_base))

_root = _base.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

