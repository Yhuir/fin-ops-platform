from __future__ import annotations

import hashlib
import json
from typing import Any


def snapshot_version(snapshot: Any) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
