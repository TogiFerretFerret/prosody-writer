"""Initialize Prosodic's data directory before its first import.

Prosodic 3.10 hardcodes ~/prosodic_data. Redirect only that expansion during
import, leaving HOME, other paths, and the installed library unchanged.
Initialization happens once, before the server starts accepting work.
"""
import os
import ctypes
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
os.environ.setdefault("NLTK_DATA", str(LOCAL / "nltk_data"))
lib = LOCAL / "native/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1"
if lib.exists():
    for name in ("libpcaudio.so.0", "libsonic.so.0"):
        dependency = lib.parent / name
        if dependency.exists():
            ctypes.CDLL(str(dependency), mode=ctypes.RTLD_GLOBAL)
    os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", str(lib))
    os.environ.setdefault("ESPEAK_DATA_PATH", str(lib.parent / "espeak-ng-data"))

_expanduser = os.path.expanduser
def _data_path(path):
    if path == "~/prosodic_data":
        return str(Path(os.environ.get("PROSODY_DATA_DIR", LOCAL / "prosodic_data")))
    return _expanduser(path)

with patch("os.path.expanduser", _data_path):
    import prosodic as prosodic
