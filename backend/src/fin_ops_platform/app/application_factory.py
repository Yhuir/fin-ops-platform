from __future__ import annotations

from pathlib import Path

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.runtime_paths import default_data_dir


def create_application(*, data_dir: Path | None = None, bootstrap_mode: str | None = None) -> Application:
    return Application(
        data_dir=data_dir if data_dir is not None else default_data_dir(),
        bootstrap_mode=bootstrap_mode,
    )
