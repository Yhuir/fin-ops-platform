from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.app.server import build_application as _build_application
from fin_ops_platform.services.state_store import ApplicationStateStore


def build_local_state_application(*args, **kwargs):
    data_dir = kwargs.get("data_dir")
    if data_dir is None and args:
        data_dir = args[0]
    if data_dir is None:
        return _build_application(*args, **kwargs)

    def build_local_store(requested_data_dir: Path | None):
        if requested_data_dir is None:
            return None
        return ApplicationStateStore(requested_data_dir)

    def load_local_bootstrap_state(application: Application) -> dict[str, object]:
        load_local_pickle = getattr(getattr(application, "_state_store", None), "_load_local_pickle", None)
        loaded = load_local_pickle() if callable(load_local_pickle) else {}
        return loaded if isinstance(loaded, dict) else {}

    with (
        patch("fin_ops_platform.app.server.build_state_store", side_effect=build_local_store),
        patch.object(Application, "_runtime_bootstrap_state", load_local_bootstrap_state),
    ):
        return _build_application(*args, **kwargs)
