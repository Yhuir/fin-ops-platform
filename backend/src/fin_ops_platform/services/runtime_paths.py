from __future__ import annotations

import os
from pathlib import Path


def default_data_dir() -> Path:
    configured = os.getenv("FIN_OPS_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[4] / ".runtime" / "fin_ops_platform"
