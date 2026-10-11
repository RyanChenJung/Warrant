"""The local data directory.

Configuration and freeze files are YAML, committed to the repo and read with `yaml.safe_load`.
The data directory is per machine and never committed: it holds the downloaded release and every
database rebuilt from it.
"""

import os
from pathlib import Path

DATA_DIR_ENV = "WARRANT_DATA_DIR"
DEFAULT_DATA_DIR = Path.home() / ".cache" / "warrant"


def data_dir() -> Path:
    """Return the data directory: $WARRANT_DATA_DIR if set, else ~/.cache/warrant."""
    return Path(os.environ.get(DATA_DIR_ENV, DEFAULT_DATA_DIR)).expanduser()
